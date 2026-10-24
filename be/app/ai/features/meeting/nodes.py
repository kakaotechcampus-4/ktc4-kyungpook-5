"""회의 발화 하나를 판단하고, 필요하면 기록을 찾아 답을 만든다.

모델이 만드는 값은 needs_lookup과 query 두 칸뿐이다.
route·question·trace는 코드가 규칙과 측정으로 채우므로 판단 지연에 영향이 없다.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import lru_cache

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from ...config import get_settings
from ...errors import AIError, AIInvalidResponseError, AITimeoutError
from ...llm import ainvoke_structured, build_chat_model
from ..retrieval.schemas import RecordSearchRequest
from .context import PROMPT_VERSION, build_judge_messages, meeting_date
from .schemas import (
    JudgeOutput,
    JudgeTrace,
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingProgressPort,
    QueryOutput,
    MeetingStage,
    RecordLookup,
    ToolCall,
    ToolName,
)

# 판단 호출의 제한 시간. 빨리 끊으려는 값이 아니라 무한히 기다리지 않으려는 값이다.
# 늦은 답도 띄우므로(AI-MEET-06) 드물게 늦는 호출을 버리지 않게 넉넉히 둔다.
# 측정에서 p95는 2.3초 안팎이었지만 호출 100번 중 1번꼴로 5초를 넘겼다(#114).
# 넘기면 조용히 버리지 않고 AITimeoutError로 "처리하지 못함"을 알린다.
# 검색·답 작성의 제한 시간은 그 구간을 잰 뒤 정한다.
JUDGE_TIMEOUT_SECONDS = 10.0

Judge = Callable[[list[BaseMessage]], Awaitable[JudgeOutput]]


@lru_cache(maxsize=1)
def get_judge_model() -> ChatOpenAI:
    """판단용 모델. 실시간 호출이라 추론을 끈다(#111)"""
    return build_chat_model(reasoning={"effort": "none"})


async def call_judge_model(messages: list[BaseMessage]) -> JudgeOutput:
    return await ainvoke_structured(messages, JudgeOutput, model=get_judge_model())


async def call_query_model(messages: list[BaseMessage]) -> QueryOutput:
    """검색어만 받는다. 판단 전용 모델(Laya)로 바꾸면 조회로 본 발화에만 부른다(#117).
    판단과 같은 모델·설정(추론 끔)을 써서 판단 + 검색어 호출과 지연을 견줄 수 있게 한다"""
    return await ainvoke_structured(messages, QueryOutput, model=get_judge_model())


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    lookup: RecordLookup,
    progress: MeetingProgressPort | None = None,
    judge: Judge = call_judge_model,
) -> JudgeUtteranceResult:
    """발화 하나를 판단한다. 테스트에서는 `judge`를 가짜로 바꾼다.

    판단·검색·답 작성이 실패하면 NONE이나 빈 결과로 바꾸지 않고 AI 오류 타입을 올린다.
    올리는 오류의 `trace`에는 실패하기 전까지의 판단 기록을 담는다(#117).
    """
    run = _Run()
    try:
        return await _judge(request, run, lookup=lookup, progress=progress, judge=judge)
    except AIError as error:
        error.trace = run.trace()
        raise


class _Run:
    """판단 하나를 처리하며 쌓는 기록. 성공하든 실패하든 같은 값으로 trace를 만든다"""

    def __init__(self) -> None:
        self.judge_ms = 0
        self.tool_calls: list[ToolCall] = []

    def trace(self) -> JudgeTrace:
        return JudgeTrace(
            model=get_settings().model,
            prompt_version=PROMPT_VERSION,
            judge_ms=self.judge_ms,
            tool_calls=tuple(self.tool_calls),
        )

    async def call_tool[T](
        self,
        tool: ToolName,
        query: str,
        call: Awaitable[T],
        count: Callable[[T], int] | None = None,
        prompt_version: str | None = None,
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
            )
        )
        return value


async def _judge(
    request: JudgeUtteranceRequest,
    run: _Run,
    *,
    lookup: RecordLookup,
    progress: MeetingProgressPort | None,
    judge: Judge,
) -> JudgeUtteranceResult:
    utterance_id = request.utterance.utterance_id

    async def stage(name: MeetingStage) -> None:
        if progress is not None:
            await progress.stage_changed(utterance_id, name)

    await stage("JUDGING")
    started = time.perf_counter()
    try:
        async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
            output = await judge(build_judge_messages(request))
    except TimeoutError as error:
        raise AITimeoutError("회의 판단이 제한 시간 안에 끝나지 않았습니다") from error
    finally:
        # 실패해도 실패할 때까지 걸린 시간을 남긴다
        run.judge_ms = _elapsed_ms(started)

    query = output.query.strip()
    if output.needs_lookup and not query:
        # 조회가 필요하다면서 검색어가 없으면 찾을 수 없다. NONE으로 바꾸면 놓친 질문이 된다
        raise AIInvalidResponseError("조회가 필요하다는 판단에 검색어가 없습니다")

    def result(**fields) -> JudgeUtteranceResult:
        return JudgeUtteranceResult(
            utterance_id=utterance_id,
            source_version=request.utterance.version,
            trace=run.trace(),
            **fields,
        )

    if not output.needs_lookup:
        # needs_lookup이 false면 모델이 검색어를 적어 와도 쓰지 않는다
        return result(route="NONE", kind="NO_LOOKUP")

    # 검색어는 판단이 이미 정리했으므로 그대로 찾는다. 기준일은 회의 날짜다
    search = RecordSearchRequest(
        club_id=request.club_id, query=query, today=meeting_date(request)
    )
    await stage("SEARCHING")
    chunks = await run.call_tool("records.search", query, lookup.search(search), count=len)
    if not chunks:
        return result(route="RAG", kind="NOT_FOUND", question=query)

    await stage("ANSWERING")
    answer = await run.call_tool(
        "llm.generate",
        query,
        lookup.answer(search, chunks),
        prompt_version=lookup.answer_prompt_version,
    )
    if answer is None:
        return result(route="RAG", kind="NOT_FOUND", question=query)

    found = {chunk.source for chunk in chunks}
    if any(source not in found for source in answer.sources):
        # 검색되지 않은 기록을 출처로 내보내지 않는다(AI-RET-02)
        raise AIInvalidResponseError("답의 출처가 검색된 기록에 없습니다")
    return result(
        route="RAG",
        kind="ANSWER",
        question=query,
        answer=answer.answer,
        sources=answer.sources,
    )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
