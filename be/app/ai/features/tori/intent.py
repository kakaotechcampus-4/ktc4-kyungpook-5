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


class ToriIntentResult(ContractModel):
    intent: Literal['record_search', 'task_list', 'event_planning', 'meeting', 'clarify', 'unsupported']
    query: NonBlankStr | None = None
    scope: Literal['self', 'all'] | None = None
    kind: Literal['task', 'schedule', 'all'] | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode='after')
    def validate_fields(self) -> Self:
        if (self.intent == 'record_search') != (self.query is not None):
            raise ValueError('자료 검색에만 검색어가 필요합니다')
        if self.intent != 'task_list' and any(x is not None for x in (self.scope, self.kind, self.date_from, self.date_to)):
            raise ValueError('일정 검색 필드는 조회 요청에만 허용됩니다')
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('날짜 범위 순서가 잘못됐습니다')
        return self


_PROMPT = Path(__file__).with_suffix('.md').read_text(encoding='utf-8')


async def classify_tori_intent(request: ToriIntentRequest) -> ToriIntentResult:
    # 원문은 별도 사용자 메시지로 넘기며 반환 분류는 실행 권한이 아니다.
    messages = [SystemMessage(_PROMPT), HumanMessage(
        f'기준일: {request.reference_date.isoformat()}\n시간대: {request.timezone}\n사용자 발화: {request.message}')]
    return await ainvoke_structured(messages, ToriIntentResult)
