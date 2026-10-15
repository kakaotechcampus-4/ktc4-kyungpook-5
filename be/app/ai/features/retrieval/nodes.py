"""기록 검색·근거 구성 처리 단계를 정의한다.

    rewrite_query → retrieve → assess ─(근거 부족, 회차 남음)→ retrieve
                                     └→ build_result

각 단계는 상태를 받아 바뀐 값만 돌려준다. 그래프로 옮길 때 노드로 그대로 쓴다.
"""

from collections.abc import Awaitable, Callable
from html import escape
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from ...contracts import RecordSource
from ...errors import AIInvalidResponseError
from ...llm import aembed_texts, ainvoke_structured
from ...ports import ChunkSearchQuery, RecordSearchPort, RetrievedChunk
from .indexing import Embed
from .schemas import (
    EvidenceAssessment,
    EvidenceItem,
    RecordConflict,
    RecordFact,
    RecordSearchRequest,
    RecordSearchResult,
    SearchQueries,
    SearchState,
)

# 첫 검색을 포함한 검색 횟수. 재검색은 측정에서 나아진 것 없이 틀린 사실과 시간만 늘어
# 기본은 한 번만 찾는다(docs/retrieval-evaluation.md 2026-10-15 #72)
MAX_SEARCH_ROUNDS = 1
# 한 번에 찾는 검색어 수. 프롬프트도 1~3개로 안내한다
MAX_QUERIES = 3

_PROMPTS = Path(__file__).parent / "prompts"
REWRITE_QUERY_PROMPT = (_PROMPTS / "rewrite_query.md").read_text(encoding="utf-8")
ASSESS_EVIDENCE_PROMPT = (_PROMPTS / "assess_evidence.md").read_text(encoding="utf-8")

Invoke = Callable[[list[BaseMessage], type[BaseModel]], Awaitable[BaseModel]]


async def search_records(
    request: RecordSearchRequest,
    *,
    port: RecordSearchPort,
    embed: Embed = aembed_texts,
    invoke: Invoke = ainvoke_structured,
    max_rounds: int = MAX_SEARCH_ROUNDS,
    rewrite: bool = True,
) -> RecordSearchResult:
    """동아리 기록에서 찾을 내용의 근거를 찾아 사실·확인하지 못한 것·자료 간 차이로 돌려준다.

    관련 기록이 없으면 출처 없이 찾지 못했다는 결과를 돌려준다. 오류가 아니다.
    모델·임베딩 호출이 실패하면 AI 오류 타입이 그대로 올라간다.
    테스트에서는 `embed`와 `invoke`를 가짜로 바꾼다.

    호출하는 쪽의 조건에 맞춰 바꿀 수 있다. 회의 어시스턴트처럼 검색어를 이미 만든 경우
    `rewrite=False`로 검색어 정리를 건너뛰고 `query`를 그대로 검색어로 쓴다.
    `max_rounds`는 재검색까지 포함한 검색 횟수이고, 판단 모델은 모델을 정한 `invoke`를 넘겨 바꾼다.
    """
    state: SearchState = {
        "request": request,
        "queries": [],
        "searched": [],
        "chunks": [],
        "rounds": 0,
        "assessment": None,
        "result": None,
    }
    if rewrite:
        state.update(await rewrite_query(state, invoke=invoke))
    else:
        state["queries"] = [request.query]
    while True:
        found_before = len(state["chunks"])
        state.update(await retrieve(state, port=port, embed=embed))
        # 청크가 하나도 없으면 동아리에 기록이 없는 것이라 다시 찾아도 같다.
        # 재검색에서 새 청크가 없으면 같은 자료로 다시 판단할 이유가 없다.
        if len(state["chunks"]) == found_before:
            break
        state.update(await assess(state, invoke=invoke, max_rounds=max_rounds))
        # 근거가 충분하거나 회차를 다 쓰면 assess가 다음 검색어를 비운다
        if not state["queries"]:
            break
    state.update(build_result(state))
    return state["result"]


async def rewrite_query(state: SearchState, *, invoke: Invoke) -> dict:
    """찾을 내용과 행사 맥락으로 검색어를 정리한다"""
    messages = [
        SystemMessage(REWRITE_QUERY_PROMPT),
        HumanMessage(_request_context(state["request"])),
    ]
    output = await invoke(messages, SearchQueries)
    queries = _clean_queries(output.queries, searched=[])
    if not queries:
        raise AIInvalidResponseError("모델이 검색어를 정리하지 못했습니다")
    return {"queries": queries}


async def retrieve(state: SearchState, *, port: RecordSearchPort, embed: Embed) -> dict:
    """검색어마다 비슷한 청크를 찾아 지금까지 찾은 청크 뒤에 붙인다"""
    request = state["request"]
    queries = state["queries"]
    chunks = list(state["chunks"])
    seen = {_chunk_key(chunk) for chunk in chunks}

    vectors = await embed(queries)
    # BE 구현체가 DB 세션 하나를 쓸 수 있어 동시에 부르지 않는다
    for vector in vectors:
        found = await port.search_chunks(
            ChunkSearchQuery(
                club_id=request.club_id,
                embedding=vector,
                limit=request.limit,
                category=request.category,
                event_id=request.event_id,
            )
        )
        for chunk in found:
            key = _chunk_key(chunk)
            if key not in seen:
                seen.add(key)
                chunks.append(chunk)

    return {
        "chunks": chunks,
        "searched": state["searched"] + queries,
        "queries": [],
        "rounds": state["rounds"] + 1,
    }


async def assess(
    state: SearchState, *, invoke: Invoke, max_rounds: int = MAX_SEARCH_ROUNDS
) -> dict:
    """근거가 충분한지 판단하고 지금 자료로 결과를 구성한다. 부족하면 다음 검색어를 남긴다"""
    retries_left = max_rounds - state["rounds"]
    messages = [
        SystemMessage(ASSESS_EVIDENCE_PROMPT),
        HumanMessage(
            f"{_request_context(state['request'])}\n"
            f"앞서 찾은 검색어: {', '.join(state['searched'])}\n"
            f"다시 찾을 수 있는 횟수: {retries_left}\n\n"
            f"찾은 자료\n\n{_format_chunks(state['chunks'])}"
        ),
    ]
    assessment = await invoke(messages, EvidenceAssessment)
    queries = (
        _clean_queries(assessment.retry_queries, searched=state["searched"])
        if retries_left > 0 and not assessment.sufficient
        else []
    )
    return {"assessment": assessment, "queries": queries}


def build_result(state: SearchState) -> dict:
    """자료 id를 검색된 청크의 출처로 바꿔 결과를 만든다"""
    request = state["request"]
    assessment = state["assessment"]
    if assessment is None:
        return {"result": RecordSearchResult(not_found=(request.query,))}

    by_id = {_chunk_id(index): chunk for index, chunk in enumerate(state["chunks"])}
    try:
        result = RecordSearchResult(
            facts=tuple(_fact(item, by_id) for item in assessment.facts),
            not_found=tuple(assessment.not_found),
            conflicts=tuple(
                RecordConflict(
                    description=conflict.description,
                    values=tuple(_fact(item, by_id) for item in conflict.values),
                )
                for conflict in assessment.conflicts
            ),
        )
    except ValidationError as error:
        raise AIInvalidResponseError(
            "기록 검색 결과가 RecordSearchResult 형식과 맞지 않습니다"
        ) from error
    return {"result": result}


def _fact(item: EvidenceItem, by_id: dict[str, RetrievedChunk]) -> RecordFact:
    unknown = [chunk_id for chunk_id in item.chunk_ids if chunk_id not in by_id]
    if unknown:
        raise AIInvalidResponseError(
            f"모델이 찾지 않은 자료를 출처로 가리켰습니다: {', '.join(unknown)}"
        )
    # 같은 위치의 청크가 여러 개면 출처가 겹치므로 한 번만 남긴다
    sources: list[RecordSource] = []
    for chunk_id in item.chunk_ids:
        source = by_id[chunk_id].source
        if source not in sources:
            sources.append(source)
    return RecordFact(content=item.content, sources=tuple(sources))


def _request_context(request: RecordSearchRequest) -> str:
    lines = [f"오늘: {request.today.isoformat()}", f"찾을 내용: {request.query}"]
    if request.conditions is not None:
        # 검색에는 행사 종류와 시기만 쓴다. 계획 중인 인원·회비·장소를 넘기면
        # 검색어가 계획값으로 좁혀지거나 근거 판단에서 기록 속 값과 섞일 수 있다
        conditions = request.conditions.model_dump(
            mode="json", include={"event_type", "start_date"}, exclude_none=True
        )
        if conditions:
            lines.append(
                "계획 중인 행사: "
                + ", ".join(f"{key}={value}" for key, value in conditions.items())
            )
    return "\n".join(lines)


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    """자료를 <record>로 감싼다. 원문의 꺾쇠를 바꿔 자료가 감싼 구역 밖으로 나가지 못하게 한다"""
    return "\n\n".join(
        f'<record id="{_chunk_id(index)}" file="{escape(chunk.source.file_name)}" '
        f'location="{escape(chunk.source.location.label)}">\n'
        f"{escape(chunk.text, quote=False)}\n</record>"
        for index, chunk in enumerate(chunks)
    )


def _clean_queries(queries: list[str], *, searched: list[str]) -> list[str]:
    cleaned: list[str] = []
    for query in queries:
        query = query.strip()
        if query and query not in searched and query not in cleaned:
            cleaned.append(query)
    return cleaned[:MAX_QUERIES]


def _chunk_id(index: int) -> str:
    return f"c{index + 1}"


def _chunk_key(chunk: RetrievedChunk) -> tuple[str, str, str]:
    # 긴 섹션을 겹쳐 자르면 같은 라벨의 청크가 여럿이라 본문까지 본다
    return (chunk.source.record_id, chunk.source.location.label, chunk.text)
