"""생성 입력·모델 출력·검증된 화면 초안을 구분한다."""

from ....contracts import (valid_timezone, ChatGenerationTrigger, ButtonGenerationTrigger,
    PlanAction, PlanStepFields, ExcludedPlanStep, PreviewStep, PlanAssumption,
    EventPlanPreview, PlanGenerationResult, GenerationOffer, PlanningGenerationState)


from typing import Protocol

from pydantic import Field, field_validator

from ....contracts import ChatTurn, ContractModel, NonBlankStr, RecordFact, PlanningDraft, CalendarDate


# 모델 출력과 검증된 초안은 공통 필드만 공유한다.
class ModelStep(PlanStepFields):
    pass


class PlanGenerationInput(ContractModel):
    basis_draft: PlanningDraft
    trigger: ChatGenerationTrigger | ButtonGenerationTrigger
    messages: tuple[ChatTurn, ...] = ()
    reference_date: CalendarDate
    timezone: NonBlankStr = "Asia/Seoul"
    reference_facts: tuple[RecordFact, ...] = ()

    _timezone = field_validator("timezone")(valid_timezone)


class ModelAssumption(ContractModel):
    content: NonBlankStr
    fact_ids: tuple[NonBlankStr, ...] = ()


class PlanComposition(ContractModel):
    """LLM의 구조화 출력. 이름·담당·출처 객체는 모델이 쓰지 않는다."""
    steps: tuple[ModelStep, ...] = Field(min_length=1, max_length=13)
    excluded_steps: tuple[ExcludedPlanStep, ...] = ()
    assumptions: tuple[ModelAssumption, ...] = ()
    open_questions: tuple[NonBlankStr, ...] = ()
    warnings: tuple[NonBlankStr, ...] = ()


class PlanGenerator(Protocol):
    async def __call__(self, request: PlanGenerationInput) -> PlanGenerationResult: ...
