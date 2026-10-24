"""생성 입력·모델 출력·검증된 화면 초안을 구분한다."""

from typing import Literal, Protocol, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.core.enums import ActionType, StepActor, StepCode, StepPhase

from ....contracts import ChatTurn, ContractModel, NonBlankStr, RecordSource
from ...retrieval.schemas import RecordFact
from ..agent.state import PlanningDraft
from ..schemas import CalendarDate, ConditionField


def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("유효한 IANA 시간대가 필요합니다") from error
    return value


class ChatGenerationTrigger(ContractModel):
    source: Literal["chat"] = "chat"
    request_id: NonBlankStr  # 이번 사용자 메시지 ID
    quote: NonBlankStr


class ButtonGenerationTrigger(ContractModel):
    source: Literal["button"] = "button"
    request_id: NonBlankStr  # 호출자가 만든 클릭 요청 ID. 채팅 근거를 요구하지 않는다.


class PlanGenerationInput(ContractModel):
    basis_draft: PlanningDraft
    trigger: ChatGenerationTrigger | ButtonGenerationTrigger
    messages: tuple[ChatTurn, ...] = ()
    reference_date: CalendarDate
    timezone: NonBlankStr = "Asia/Seoul"
    reference_facts: tuple[RecordFact, ...] = ()

    _timezone = field_validator("timezone")(valid_timezone)


class PlanAction(ContractModel):
    type: ActionType
    title: NonBlankStr
    due_date: CalendarDate | None = None


class ModelStep(ContractModel):
    code: StepCode
    purpose: NonBlankStr
    starts_at: AwareDatetime | None = None
    deadline: AwareDatetime | None = None
    actions: tuple[PlanAction, ...] = ()


class ExcludedPlanStep(ContractModel):
    code: StepCode
    reason: NonBlankStr


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


class PreviewStep(ModelStep):
    name: NonBlankStr
    phase: StepPhase
    actor: StepActor


class PlanAssumption(ContractModel):
    content: NonBlankStr
    sources: tuple[RecordSource, ...] = ()


class EventPlanPreview(ContractModel):
    id: NonBlankStr  # 로컬에서 참조할 임시 ID. BE의 Step/Plan ID가 아니다.
    basis_draft: PlanningDraft
    trigger: ChatGenerationTrigger | ButtonGenerationTrigger
    steps: tuple[PreviewStep, ...] = Field(min_length=1)
    excluded_steps: tuple[ExcludedPlanStep, ...]
    assumptions: tuple[PlanAssumption, ...] = ()
    open_questions: tuple[NonBlankStr, ...] = ()
    warnings: tuple[NonBlankStr, ...] = ()


class PlanGenerationResult(ContractModel):
    status: Literal["generated", "needs_clarification", "failed"]
    preview: EventPlanPreview | None = None
    reason: NonBlankStr | None = None
    model_calls: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status == "generated":
            if self.preview is None or self.reason is not None:
                raise ValueError("생성 성공에는 계획 초안만 필요합니다")
        elif self.preview is not None or self.reason is None:
            raise ValueError("생성 보류·실패에는 이유만 필요합니다")
        return self


class PlanGenerator(Protocol):
    async def __call__(self, request: PlanGenerationInput) -> PlanGenerationResult: ...


class GenerationOffer(ContractModel):
    id: NonBlankStr
    status: Literal["pending", "deferred"]
    summary: NonBlankStr
    basis_draft: PlanningDraft


class PlanningGenerationState(ContractModel):
    offer: GenerationOffer | None = None
    preview: EventPlanPreview | None = None
    # 거절된 조건 변경이 남으면 옛 값으로 조용히 생성하지 않는다.
    condition_change_pending: bool = False
    pending_condition_fields: tuple[ConditionField, ...] = ()

    @model_validator(mode="after")
    def _pending_fields(self) -> Self:
        if self.pending_condition_fields and not self.condition_change_pending:
            raise ValueError("미해결 조건 필드가 있으면 변경 확인도 필요합니다")
        return self
