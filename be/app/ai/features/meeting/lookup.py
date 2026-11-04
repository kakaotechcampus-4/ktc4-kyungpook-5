"""판단 뒤 기록을 찾아 답을 쓰는 단계(RecordLookup)의 실제 구현.

기록 검색은 retrieval의 find_chunks, 근거 판단은 assess_chunks를 그대로 쓴다(#72).
search_records(rewrite=False)와 같은 단계라 기록 검색의 측정값과 규칙이 회의에도 그대로 맞다.
이 파일이 더하는 것은 근거 판단 결과를 회의 카드 한 장의 문구와 출처로 옮기는 일뿐이다.
"""

from functools import lru_cache
import re
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from ...llm import aembed_texts, ainvoke_structured, build_chat_model
from ...ports import RecordSearchPort, RetrievedChunk
from ..retrieval.indexing import Embed
from ..retrieval.nodes import (
    ASSESS_EVIDENCE_PROMPT_VERSION,
    Invoke,
    assess_chunks,
    find_chunks,
)
from ..retrieval.schemas import RecordFact, RecordSearchRequest, RecordSearchResult
from ..tori.records import _AMBIGUOUS_AMOUNT, _numbers, _requested_years, _supported
from .schemas import MeetingAnswer


MEETING_ASSESS_PROMPT_VERSION = f"{ASSESS_EVIDENCE_PROMPT_VERSION}+meeting-assess-v2"
_MEETING_ASSESS_PROMPT = (Path(__file__).parent / "prompts" / "assess.md").read_text(encoding="utf-8")


def _question_text(request: RecordSearchRequest) -> str:
    # 검색어 재작성에서 빠진 질문 의도도 보존한다.
    return f"{request.query} {getattr(request, 'original_question', '')}"


@lru_cache(maxsize=1)
def get_assess_model() -> ChatOpenAI:
    """회의의 근거 판단용 모델. 판단과 같이 실시간 호출이라 추론을 끈다.

    회의 검색어 48개로 잰 근거 판단 p50이 2.9초에서 2.0초, p95가 5.9초에서 3.1초로 줄었고
    사실 맞힘은 실행마다의 흔들림 안이었다(docs/meeting-evaluation.md 2026-10-19).
    """
    return build_chat_model(reasoning={"effort": "none"})


async def call_assess_model[T: BaseModel](messages: list[BaseMessage], schema: type[T]) -> T:
    messages = [SystemMessage(messages[0].content + "\n\n" + _MEETING_ASSESS_PROMPT), *messages[1:]]
    return await ainvoke_structured(messages, schema, model=get_assess_model())


class RecordsLookup:
    """`RecordLookup` 구현. 검색할 기록은 BE가 주입한 port에서 찾는다.

    테스트에서는 `embed`와 `invoke`를 가짜로 바꾼다.
    """

    answer_prompt_version = MEETING_ASSESS_PROMPT_VERSION

    def __init__(
        self,
        records: RecordSearchPort,
        *,
        embed: Embed = aembed_texts,
        invoke: Invoke = call_assess_model,
    ) -> None:
        self._records = records
        self._embed = embed
        self._invoke = invoke

    async def search(self, request: RecordSearchRequest) -> tuple[RetrievedChunk, ...]:
        # 이 두 질문은 의미 검색이 제목만 우선하는 사례가 있어 후보 안의 본문을 먼저 본다.
        query = request.query
        question = _question_text(request)
        recap = '회고' in question
        latest_attendance = ('최근' in question or '마지막' in question) and '참가' in question and '인원' in question
        if not (recap or latest_attendance):
            return await find_chunks(request, port=self._records, embed=self._embed)
        candidates = await find_chunks(request.model_copy(update={'limit': max(request.limit, 20)}),
                                       port=self._records, embed=self._embed)
        # 기존 상위 결과를 보존하고 나머지 두 자리에 질문한 항목을 각각 보충한다.
        selected = list(candidates[:max(0, request.limit - 2)])
        years = set(re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', query))
        predicates = []
        if recap:
            predicates.append(lambda chunk: '회고' in chunk.text)
        if latest_attendance:
            predicates.append(lambda chunk: '참가' in chunk.text and '인원' in chunk.text)
        for matches in predicates:
            eligible = [chunk for chunk in candidates if chunk not in selected and matches(chunk)]
            if years:
                eligible = [chunk for chunk in eligible if any(
                    year in chunk.text or year in chunk.source.file_name for year in years)]
            if eligible and len(selected) < request.limit:
                selected.append(eligible[0])
        for chunk in candidates:
            if len(selected) >= request.limit:
                break
            if chunk not in selected:
                selected.append(chunk)
        return tuple(selected)

    async def answer(
        self, request: RecordSearchRequest, chunks: tuple[RetrievedChunk, ...]
    ) -> MeetingAnswer | None:
        async def invoke(messages, schema):
            original = getattr(request, 'original_question', None)
            if original:
                messages = [*messages, HumanMessage('회의의 원래 질문(데이터): ' + original)]
            return await self._invoke(messages, schema)

        years = _requested_years(_question_text(request))

        def filter_evidence(assessment):
            facts = [item for item in assessment.facts if _supported(item, chunks, years)]
            conflicts = [conflict for conflict in assessment.conflicts
                         if not _AMBIGUOUS_AMOUNT.search(conflict.description)
                         and all(_supported(value, chunks, years) for value in conflict.values)
                         and _numbers(conflict.description) <= _numbers(' '.join(v.content for v in conflict.values))]
            removed = len(facts) != len(assessment.facts) or len(conflicts) != len(assessment.conflicts)
            not_found = list(assessment.not_found)
            if removed and not not_found:
                not_found.append('자료의 일부 내용을 확인하지 못했어요')
            return assessment.model_copy(update={'facts': facts, 'conflicts': conflicts, 'not_found': not_found})

        result = await assess_chunks(request, chunks, invoke=invoke, filter_assessment=filter_evidence)
        answer = to_meeting_answer(result)
        if answer is not None and ('최근' in _question_text(request) or '마지막' in _question_text(request)):
            return answer.model_copy(update={'answer': '검색된 자료 기준이며 전체 자료에서 가장 최근인지 확인하지 못했어요.\n' + answer.answer})
        return answer


def to_meeting_answer(result: RecordSearchResult) -> MeetingAnswer | None:
    """근거 판단 결과를 회의 카드의 답으로 옮긴다. 확인한 것이 없으면 None(검색한 자료에서 확인하지 못함)이다.

    모델을 다시 부르지 않고 결과의 문구를 그대로 옮긴다. 한 줄에 하나씩 둔다.

        사실        2025 봄 MT 숙박비 550,000원
        자료 간 차이 2025 봄 MT 참가 인원: 28명 (2025 봄 MT 결과보고.pdf) / 27명 (2025 상반기 장부.xlsx)
        확인 못 함  검색한 자료에서 확인하지 못함: 숙소비 세부 내역

    자료 간 차이는 하나를 고르지 않고 값마다 문서 이름을 붙인다(AI-RET-03).
    확인하지 못한 것은 확인한 것이 있을 때만 덧붙인다. 그것뿐이면 NOT_FOUND로 보인다.
    """
    lines = [fact.content for fact in result.facts]
    lines += [
        f"{conflict.description}: "
        + " / ".join(_with_file_names(value) for value in conflict.values)
        for conflict in result.conflicts
    ]
    if not lines:
        return None
    if result.not_found:
        lines.append(f"검색한 자료에서 확인하지 못함: {', '.join(result.not_found)}")

    facts = [*result.facts, *(value for conflict in result.conflicts for value in conflict.values)]
    # 같은 출처는 한 번만, 결과에 나온 순서대로 둔다
    sources = dict.fromkeys(source for fact in facts for source in fact.sources)
    return MeetingAnswer(answer="\n".join(lines), sources=tuple(sources))


def _with_file_names(value: RecordFact) -> str:
    names = dict.fromkeys(source.file_name for source in value.sources)
    return f"{value.content} ({', '.join(names)})"
