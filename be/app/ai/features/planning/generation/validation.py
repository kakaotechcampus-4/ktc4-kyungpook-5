"""계획 검증의 첫 위반을 설명한다. 공개 응답이나 운영 로그에는 세부 값을 추가하지 않는다."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.core.enums import StepCode
from ....errors import AIInvalidResponseError


PlanValidationRule = Literal[
    'catalog_partition', 'phase_order', 'reversed_period', 'dates_when_unknown',
    'action_type', 'action_due_outside_step', 'before_event_after_start',
    'event_start_mismatch', 'event_end_mismatch', 'after_event_before_end', 'unknown_fact_id',
]

# 기존 안내 문구를 유지한다. 진단기는 문구를 해석하지 않고 rule을 읽는다.
MESSAGES: dict[PlanValidationRule, str] = {
    'catalog_partition': '계획의 포함·제외 단계가 카탈로그와 맞지 않아요.',
    'phase_order': '계획의 세 묶음 순서가 맞지 않아요.',
    'reversed_period': '단계 마감이 시작보다 빨라요.',
    'dates_when_unknown': '행사 날짜가 미정이면 단계 날짜와 기한도 미정으로 남겨야 해요.',
    'action_type': '단계에서 허용하지 않은 예정 행동이 있어요.',
    'action_due_outside_step': '예정 행동의 기한이 단계 기간 밖에 있어요.',
    'before_event_after_start': '행사 전에 할 단계가 행사 시작 뒤로 잡혔어요.',
    'event_start_mismatch': '행사 당일 단계의 시작일이 현재 조건과 달라요.',
    'event_end_mismatch': '행사 당일 단계의 종료일이 현재 조건과 달라요.',
    'after_event_before_end': '행사 뒤에 할 단계가 종료 전으로 잡혔어요.',
    'unknown_fact_id': '제공하지 않은 기록 근거가 계획에 포함됐어요.',
}


class PlanValidationViolation(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')

    rule: PlanValidationRule
    # JSON Pointer: 빈 문자열은 초안 전체, /steps/2는 세 번째 단계다.
    path: str = Field(pattern=r'^(?:/.*)?$')
    step_code: StepCode | None = None
    action_index: int | None = Field(default=None, ge=0)
    expected: JsonValue
    actual: JsonValue
    timezone: str | None = None


class PlanValidationError(AIInvalidResponseError):
    """기존 오류로 처리되되, 합성 진단 실행에서만 구조화 정보를 수집할 수 있다."""

    def __init__(self, violation: PlanValidationViolation):
        self.violation = violation.model_copy(deep=True)
        super().__init__(MESSAGES[violation.rule])
