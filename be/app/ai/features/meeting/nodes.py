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
from ...errors import AIInvalidResponseError, AITimeoutError
from ...llm import ainvoke_structured, build_chat_model
from .context import PROMPT_VERSION, build_judge_messages
from .schemas import (
    JudgeOutput,
    JudgeTrace,
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingProgressPort,
    MeetingStage,
    RecordLookup,
    ToolCall,
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


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    lookup: RecordLookup,
    progress: MeetingProgressPort | None = None,
    judge: Judge = call_judge_model,
) -> JudgeUtteranceResult:
    """발화 하나를 판단한다. 테스트에서는 `judge`를 가짜로 바꾼다.

    판단·검색·답 작성이 실패하면 NONE이나 빈 결과로 바꾸지 않고 AI 오류 타입을 올린다.
    """
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
    judge_ms = _elapsed_ms(started)

    query = output.query.strip()
    if output.needs_lookup and not query:
        # 조회가 필요하다면서 검색어가 없으면 찾을 수 없다. NONE으로 바꾸면 놓친 질문이 된다
        raise AIInvalidResponseError("조회가 필요하다는 판단에 검색어가 없습니다")

    tool_calls: list[ToolCall] = []

    def result(**fields) -> JudgeUtteranceResult:
        return JudgeUtteranceResult(
            utterance_id=utterance_id,
            source_version=request.utterance.version,
            trace=JudgeTrace(
                model=get_settings().model,
                prompt_version=PROMPT_VERSION,
                judge_ms=judge_ms,
                tool_calls=tuple(tool_calls),
            ),
            **fields,
        )

    if not output.needs_lookup:
        # needs_lookup이 false면 모델이 검색어를 적어 와도 쓰지 않는다
        return result(route="NONE", kind="NO_LOOKUP")

    await stage("SEARCHING")
    started = time.perf_counter()
    chunks = await lookup.search(request.club_id, query)
    tool_calls.append(
        ToolCall(
            tool="records.search",
            input=query,
            status="OK",
            duration_ms=_elapsed_ms(started),
            result_count=len(chunks),
        )
    )
    if not chunks:
        return result(route="RAG", kind="NOT_FOUND", question=query)

    await stage("ANSWERING")
    started = time.perf_counter()
    answer = await lookup.answer(query, chunks)
    tool_calls.append(
        ToolCall(
            tool="llm.generate",
            input=query,
            status="OK",
            duration_ms=_elapsed_ms(started),
        )
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
