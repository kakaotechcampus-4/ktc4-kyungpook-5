"""회의 발화 하나를 판단하고, 필요하면 기록을 찾아 답을 만든다.

판단은 판단 전용 API Jev가 하고, 조회로 본 발화에만 luna를 불러 검색어를 받는다(#255).

    발화 → Jev: 조회가 필요할 확률 ─┬ 0.35 미만 → NONE (luna를 부르지 않음)
                                     └ 0.35 이상 → luna: 검색어 → 기록 검색 → 답

모델이 만드는 값은 확률과 검색어뿐이다. route·question·trace는 코드가 채운다.
luna가 판단과 검색어를 함께 받던 call_judge_model은 측정 스크립트와 회의 뒤 비교에 쓰려고 남긴다.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from ...errors import AIError, AIInvalidResponseError, AITimeoutError
from ...llm import ainvoke_structured, build_chat_model
from .context import (
    JEV_MODEL,
    JEV_THRESHOLD,
    QUERY_PROMPT_VERSION,
    build_judge_input,
    build_query_messages,
    meeting_date,
)
from .jev import JevDecision, call_jev_decision
from .questions import QUESTIONS_VERSION
from .schemas import (
    JudgeOutput,
    JudgeTrace,
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingProgressPort,
    QueryOutput,
    MeetingStage,
    MeetingSearchRequest,
    RecordLookup,
    ToolCall,
    ToolName,
)

# 판단 단계(Jev 판단 + 조회일 때 검색어)의 제한 시간. 빨리 끊으려는 값이 아니라 무한히 기다리지 않으려는 값이다.
# 늦은 답도 띄우므로(AI-MEET-06) 드물게 늦는 호출을 버리지 않게 넉넉히 둔다.
# luna 판단을 잰 측정에서 p95는 2.3초 안팎이었지만 호출 100번 중 1번꼴로 5초를 넘겼다(#114).
# Jev 경로는 조회할 말에서 p95 3.34초였다(#245).
# 넘기면 조용히 버리지 않고 AITimeoutError로 "처리하지 못함"을 알린다.
# 검색·답 작성의 제한 시간은 그 구간을 잰 뒤 정한다.
JUDGE_TIMEOUT_SECONDS = 10.0

# 입력 글 → 조회가 필요할 확률. 기본은 Jev(call_jev)이고 테스트에서는 가짜로 바꾼다
Decide = Callable[[str], Awaitable[float | JevDecision]]
# 기존 테스트·도구가 교체하던 이름을 유지하되, 기본 경로는 두 확률을 받는다.
call_jev = call_jev_decision
# 검색어 지시문 → 검색어. 기본은 luna(call_query_model)
Query = Callable[[list[BaseMessage]], Awaitable[QueryOutput]]


@lru_cache(maxsize=1)
def get_judge_model() -> ChatOpenAI:
    """판단용 모델. 실시간 호출이라 추론을 끈다(#111)"""
    return build_chat_model(reasoning={"effort": "none"})


async def call_judge_model(messages: list[BaseMessage]) -> JudgeOutput:
    """luna가 판단과 검색어를 함께 낸다. 회의 판단에는 쓰지 않고 측정·비교에 쓴다(#255)"""
    return await ainvoke_structured(messages, JudgeOutput, model=get_judge_model())


async def call_query_model(messages: list[BaseMessage]) -> QueryOutput:
    """검색어만 받는다. Jev가 조회로 본 발화에만 부른다(#255).
    luna 판단과 같은 모델·설정(추론 끔)이라 측정(#245)의 지연이 이어진다"""
    return await ainvoke_structured(messages, QueryOutput, model=get_judge_model())


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    lookup: RecordLookup,
    progress: MeetingProgressPort | None = None,
    decide: Decide | None = None,
    query: Query | None = None,
) -> JudgeUtteranceResult:
    """발화 하나를 판단한다. 테스트에서는 `decide`·`query`를 가짜로 바꾼다.

    넘기지 않으면 Jev(call_jev)와 luna(call_query_model)를 부른다. 부를 때 이 모듈에서 찾으므로
    BE 통합 테스트처럼 공개 경계로 들어오는 경우에도 nodes.call_jev를 바꿔 가짜로 둘 수 있다.

    판단·검색·답 작성이 실패하면 NONE이나 빈 결과로 바꾸지 않고 AI 오류 타입을 올린다.
    올리는 오류의 `trace`에는 실패하기 전까지의 판단 기록을 담는다(#117).
    """
    run = _Run()
    try:
        return await _judge(
            request,
            run,
            lookup=lookup,
            progress=progress,
            decide=decide or call_jev,
            query=query or call_query_model,
        )
    except AIError as error:
        error.trace = run.trace()
        raise


class _Run:
    """판단 하나를 처리하며 쌓는 기록. 성공하든 실패하든 같은 값으로 trace를 만든다"""

    def __init__(self) -> None:
        self.judge_ms = 0
        self.web_search_probability: float | None = None
        self.tool_calls: list[ToolCall] = []

    def trace(self) -> JudgeTrace:
        return JudgeTrace(
            model=JEV_MODEL,
            prompt_version=QUESTIONS_VERSION,
            judge_ms=self.judge_ms,
            web_search_probability=self.web_search_probability,
            tool_calls=tuple(self.tool_calls),
        )

    async def call_tool[T](
        self,
        tool: ToolName,
        query: str,
        call: Awaitable[T],
        count: Callable[[T], int] | None = None,
        prompt_version: str | None = None,
        probability: Callable[[T], float] | None = None,
    ) -> T:
        """도구를 부르고 결과와 걸린 시간을 남긴다. 실패해도 남기고 오류는 그대로 올린다"""
        started = time.perf_counter()
        try:
            value = await call
        except AIError as error:
            status = "TIMEOUT" if isinstance(error, AITimeoutError) else "FAILED"
            self.tool_calls.append(
                ToolCall(
                    tool=tool,
                    input=query,
                    status=status,
                    duration_ms=_elapsed_ms(started),
                    prompt_version=prompt_version,
                )
            )
            raise
        self.tool_calls.append(
            ToolCall(
                tool=tool,
                input=query,
                status="OK",
                duration_ms=_elapsed_ms(started),
                result_count=count(value) if count else None,
                prompt_version=prompt_version,
                probability=probability(value) if probability else None,
            )
        )
        return value


async def _judge(
    request: JudgeUtteranceRequest,
    run: _Run,
    *,
    lookup: RecordLookup,
    progress: MeetingProgressPort | None,
    decide: Decide,
    query: Query,
) -> JudgeUtteranceResult:
    utterance_id = request.utterance.utterance_id

    async def stage(name: MeetingStage) -> None:
        if progress is not None:
            await progress.stage_changed(utterance_id, name)

    said = request.utterance.text
    await stage("JUDGING")
    started = time.perf_counter()
    try:
        async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
            decision = await run.call_tool(
                "judge.decide", said, decide(build_judge_input(request)),
                probability=lambda value: (
                    value.record_lookup if isinstance(value, JevDecision) else float(value)
                ),
            )
            if isinstance(decision, JevDecision):
                probability = decision.record_lookup
                run.web_search_probability = decision.external_web_search
            else:
                probability = decision
            needs_lookup = probability >= JEV_THRESHOLD
            searched_for = ""
            if needs_lookup:
                # Jev는 문장을 만들지 못하므로 조회로 본 발화에만 luna에게 검색어를 받는다
                output = await run.call_tool(
                    "llm.generate",
                    said,
                    query(build_query_messages(request)),
                    prompt_version=QUERY_PROMPT_VERSION,
                )
                searched_for = output.query.strip()
    except TimeoutError as error:
        raise AITimeoutError("회의 판단이 제한 시간 안에 끝나지 않았습니다") from error
    finally:
        # 실패해도 실패할 때까지 걸린 시간을 남긴다
        run.judge_ms = _elapsed_ms(started)

    if needs_lookup and not searched_for:
        # 조회가 필요하다면서 검색어가 없으면 찾을 수 없다. NONE으로 바꾸면 놓친 질문이 된다
        raise AIInvalidResponseError("조회가 필요하다는 판단에 검색어가 없습니다")

    def result(**fields) -> JudgeUtteranceResult:
        return JudgeUtteranceResult(
            utterance_id=utterance_id,
            source_version=request.utterance.version,
            trace=run.trace(),
            **fields,
        )

    if not needs_lookup:
        return result(route="NONE", kind="NO_LOOKUP")

    # 검색어는 이미 정리했으므로 그대로 찾는다. 기준일은 회의 날짜다
    search = MeetingSearchRequest(
        club_id=request.club_id, query=searched_for, today=meeting_date(request),
        original_question=request.utterance.text,
    )
    await stage("SEARCHING")
    chunks = await run.call_tool("records.search", searched_for, lookup.search(search), count=len)
    if not chunks:
        return result(route="RAG", kind="NOT_FOUND", question=searched_for)

    await stage("ANSWERING")
    answer = await run.call_tool(
        "llm.generate",
        searched_for,
        lookup.answer(search, chunks),
        prompt_version=lookup.answer_prompt_version,
    )
    if answer is None:
        return result(route="RAG", kind="NOT_FOUND", question=searched_for)

    found = {chunk.source for chunk in chunks}
    if any(source not in found for source in answer.sources):
        # 검색되지 않은 기록을 출처로 내보내지 않는다(AI-RET-02)
        raise AIInvalidResponseError("답의 출처가 검색된 기록에 없습니다")
    return result(
        route="RAG",
        kind="ANSWER",
        question=searched_for,
        answer=answer.answer,
        sources=answer.sources,
    )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
