"""메인 토리 요청을 기존 조회·진입 경계로 분류한다. 실행은 하지 않는다."""
from datetime import date
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, field_validator, model_validator

from ...contracts import ContractModel, NonBlankStr
from ...llm import ainvoke_structured


class ToriIntentRequest(ContractModel):
    message: NonBlankStr = Field(max_length=4000)
    reference_date: date
    timezone: NonBlankStr = 'Asia/Seoul'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('유효한 시간대가 필요합니다') from error
        return value


ToriIntent = Literal['record_search', 'task_list', 'event_list', 'event_planning', 'meeting', 'clarify', 'unsupported',
                     'self_intro', 'briefing', 'approval_list', 'event_status', 'meeting_tasks']
# 행사·회의 이름을 받는 분류. 이름은 발화에 있는 그대로이며 실제 행사·회의 찾기는 BE가 한다.
_TARGET_INTENTS = frozenset({'approval_list', 'event_status', 'meeting_tasks'})


class ToriIntentResult(ContractModel):
    intent: ToriIntent
    query: NonBlankStr | None = None
    scope: Literal['self', 'all'] | None = None
    kind: Literal['task', 'schedule', 'all'] | None = None
    date_from: date | None = None
    date_to: date | None = None
    event_status: Literal['PLANNING', 'ON_GOING', 'COMPLETE', 'CANCELLING', 'CANCELLED'] | None = None
    # 발화 속 행사 이름(approval_list·event_status) 또는 회의 이름(meeting_tasks). 예: "봄 MT", "11월 정기 회의"
    target: NonBlankStr | None = Field(default=None, max_length=100)
    # meeting_tasks에서 회의 날짜가 분명할 때만. "지난 회의"처럼 날짜가 없으면 null이다.
    meeting_date: date | None = None

    @model_validator(mode='after')
    def validate_fields(self) -> Self:
        if (self.intent == 'record_search') != (self.query is not None):
            raise ValueError('자료 검색에만 검색어가 필요합니다')
        if self.intent != 'task_list' and any(x is not None for x in (self.scope, self.kind, self.date_from, self.date_to)):
            raise ValueError('일정 검색 필드는 조회 요청에만 허용됩니다')
        if self.intent != 'event_list' and self.event_status is not None:
            raise ValueError('행사 상태는 행사 목록 조회에만 허용됩니다')
        if self.intent not in _TARGET_INTENTS and self.target is not None:
            raise ValueError('대상 이름은 승인 대기·행사 현황·회의 할 일 조회에만 허용됩니다')
        if self.intent != 'meeting_tasks' and self.meeting_date is not None:
            raise ValueError('회의 날짜는 회의 할 일 조회에만 허용됩니다')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('날짜 범위 순서가 잘못됐습니다')
        return self


class _ToriIntentModelResult(ToriIntentResult):
    @model_validator(mode='before')
    @classmethod
    def ignore_unused_query(cls, value):
        # 모델이 해당 분류에 쓰지 않는 검색어·대상 이름·회의 날짜를 함께 내면 그 값만 무시한다.
        # 범위·날짜처럼 조회 범위를 바꾸는 다른 필드의 불일치는 그대로 거절한다.
        if not isinstance(value, dict):
            return value
        intent = value.get('intent')
        unused = {
            'query': intent != 'record_search',
            'target': intent not in _TARGET_INTENTS,
            'meeting_date': intent != 'meeting_tasks',
        }
        return {**value, **{key: None for key, drop in unused.items() if drop and value.get(key) is not None}}


_PROMPT = Path(__file__).with_suffix('.md').read_text(encoding='utf-8')


async def classify_tori_intent(request: ToriIntentRequest) -> ToriIntentResult:
    # 원문은 별도 사용자 메시지로 넘기며 반환 분류는 실행 권한이 아니다.
    messages = [SystemMessage(_PROMPT), HumanMessage(
        f'기준일: {request.reference_date.isoformat()}\n시간대: {request.timezone}\n사용자 발화: {request.message}')]
    model_result = await ainvoke_structured(messages, _ToriIntentModelResult)
    return ToriIntentResult.model_validate(model_result.model_dump())
