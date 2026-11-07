"""생성 입력·모델 출력·검증된 화면 초안을 구분한다."""

from ....contracts import (valid_timezone, ChatGenerationTrigger, ButtonGenerationTrigger,
    PlanAction, PlanStepFields, ExcludedPlanStep, PreviewStep, PlanAssumption,
    EventPlanPreview, PlanGenerationResult, GenerationOffer, PlanningGenerationState)


from collections.abc import Awaitable, Callable
from inspect import cleandoc
from typing import Annotated, Literal, Protocol

from pydantic import Field, field_validator

from app.core.enums import StepCode

from ....contracts import ChatTurn, ContractModel, NonBlankStr, RecordFact, PlanningDraft, CalendarDate
from ....planning_catalog import PLANNING_STEP_NAMES


# 생성 모델이 고를 수 있는 단계 코드는 계획 카탈로그 13개뿐이다(#276).
# 공개 계약의 StepCode에는 운영 중 취소에 쓰는 CANCEL_* 4개도 있다. 그 목록을 그대로 보여 주면
# 모델이 "카탈로그에서 뺀 단계"로 CANCEL_*를 excluded_steps에 적어 catalog_partition 검사에서 거절됐다.
# 설명 문구는 StepCode와 같게 두어, 모델에 보이는 형식에서 바뀌는 것은 허용값 목록뿐이게 한다.
CatalogStepCode = Annotated[Literal[tuple(PLANNING_STEP_NAMES)], Field(description=cleandoc(StepCode.__doc__))]


# 모델 출력과 검증된 초안은 공통 필드만 공유한다. code만 카탈로그 13개로 좁힌다.
class ModelStep(PlanStepFields):
    code: CatalogStepCode


class ModelExcludedStep(ExcludedPlanStep):
    code: CatalogStepCode


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
    excluded_steps: tuple[ModelExcludedStep, ...] = ()
    assumptions: tuple[ModelAssumption, ...] = ()
    open_questions: tuple[NonBlankStr, ...] = ()
    warnings: tuple[NonBlankStr, ...] = ()


class PlanGenerator(Protocol):
    # on_text는 진행 알림이 있을 때만 넘긴다(#388, #389). 그래서 받지 않는 기존 생성기도 그대로 쓸 수 있다.
    async def __call__(self, request: PlanGenerationInput, *,
                       on_text: Callable[[str], Awaitable[None]] | None = None) -> PlanGenerationResult: ...
