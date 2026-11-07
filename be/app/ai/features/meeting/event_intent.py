"""회의 발화의 실제 행사 DB 조회 의도를 기존 회의 문맥으로 분류한다."""

import asyncio
import time
from pathlib import Path
from typing import Literal, Self

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, ValidationError, model_validator

from ...config import get_settings
from ...contracts import ContractModel, NonBlankStr
from ...errors import AIError, AIInvalidResponseError, AITimeoutError
from ...llm import ainvoke_structured
from .context import build_judge_input
from .event_facts import EventFactField
from .nodes import JUDGE_TIMEOUT_SECONDS, get_judge_model
from .schemas import JudgeTrace, JudgeUtteranceRequest

PROMPT_VERSION = 'meeting-event-facts-v1'
_PROMPT = (Path(__file__).parent / 'prompts' / 'event_facts.md').read_text(encoding='utf-8')


class MeetingEventIntent(ContractModel):
    disposition: Literal['lookup', 'none', 'clarify']
    scope: Literal['current', 'recent', 'selected'] | None
    fields: tuple[EventFactField, ...] = Field(max_length=5)
    event_reference: NonBlankStr | None = Field(max_length=200)

    @model_validator(mode='after')
    def valid_intent(self) -> Self:
        if self.disposition == 'lookup':
            if self.scope is None or not self.fields or len(self.fields) != len(set(self.fields)):
                raise ValueError('조회에는 범위와 중복 없는 필드가 필요합니다')
            if (self.scope == 'selected') != (self.event_reference is not None):
                raise ValueError('지정 행사 조회에만 행사 참조가 필요합니다')
        elif self.scope is not None or self.fields or self.event_reference is not None:
            raise ValueError('조회하지 않으면 범위와 필드를 비웁니다')
        return self


class MeetingEventIntentResult(ContractModel):
    intent: MeetingEventIntent
    trace: JudgeTrace


async def classify_meeting_event_facts(request: JudgeUtteranceRequest) -> MeetingEventIntentResult:
    """행사 조회 의도만 분류한다. 대상·권한·저장은 BE 책임이다."""
    started = time.perf_counter()
    def trace() -> JudgeTrace:
        return JudgeTrace(model=get_settings().model, prompt_version=PROMPT_VERSION,
                          judge_ms=round((time.perf_counter() - started) * 1000))
    try:
        async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
            intent = await ainvoke_structured(
                [SystemMessage(_PROMPT), HumanMessage(build_judge_input(request))],
                MeetingEventIntent, model=get_judge_model(),
            )
            try:
                intent = MeetingEventIntent.model_validate(intent)
            except ValidationError as error:
                raise AIInvalidResponseError('행사 조회 분류 형식이 올바르지 않습니다') from error
            if intent.event_reference is not None and intent.event_reference not in build_judge_input(request):
                raise AIInvalidResponseError('행사 참조가 회의 입력에 없습니다')
    except TimeoutError as error:
        failure = AITimeoutError('회의 행사 조회 판단이 제한 시간 안에 끝나지 않았습니다')
        failure.trace = trace()
        raise failure from error
    except AIError as error:
        error.trace = trace()
        raise
    return MeetingEventIntentResult(intent=intent, trace=trace())
