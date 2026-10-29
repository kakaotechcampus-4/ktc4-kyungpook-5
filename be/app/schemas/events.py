"""행사 도메인 요청·응답 스키마.

내부(모델·서비스)는 snake_case, API 경계는 camelCase다. 변환은 CamelModel이 맡고
서비스·모델 쪽은 이름을 바꾸지 않는다.

enum은 core/enums.py의 StrEnum을 그대로 쓴다. 값이 곧 API 코드라 변환이 필요 없다.
"""

from datetime import date
from typing import Any, Literal

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    EventType,
    MemberRole,
    StepActor,
    StepCode,
    StepPhase,
    StepState,
)
from app.schemas.common import CamelModel, PageMeta, UtcDateTime


class ResolvedBy(CamelModel):
    """승인·거절·확인요청을 처리한 동아리원."""

    id: str
    name: str
    role: MemberRole


class ActionOption(CamelModel):
    """CONFIRMATION 카드의 선택 버튼 하나."""

    key: str
    label: str


class ActionOut(CamelModel):
    id: str
    type: ActionType
    title: str
    subtitle: str | None
    # 승인 대상 본문(예: 토리가 준비한 공지 초안). 결정 검토 모달이 보여준다.
    content: str | None
    irreversible: bool
    approve_needed: bool
    status: ActionStatus
    amount: int | None
    due_date: date | None
    # CONFIRMATION은 단계에 묶이지 않아 둘 다 null이 될 수 있다.
    step_id: str | None
    step_name: str | None
    resolved_at: UtcDateTime | None
    resolved_by: ResolvedBy | None
    deny_reason: str | None
    # CONFIRMATION 전용. payload에서 펼쳐 담으며 다른 타입은 항상 null이다.
    options: list[ActionOption] | None
    allow_manual: bool | None
    can_approve: bool
    # 세부 수정 가능 여부 (#106). APPROVED에서 고치면 다시 PENDING이 된다.
    editable: bool


class ActionListResponse(CamelModel):
    data: list[ActionOut]
    meta: PageMeta


class StepProgressOut(CamelModel):
    step_order: int
    state: StepState


class EventOut(CamelModel):
    id: str
    title: str
    status: EventStatus
    start_date: date | None
    end_date: date | None
    dday: int | None
    location: str | None
    headcount: int | None
    current_step_name: str | None
    step_progress: list[StepProgressOut]
    pending_approval_count: int
    # participants·transactions 확정 전이라 항상 null (이슈 #17)
    payment: Any | None
    budget: Any | None


class EventListResponse(CamelModel):
    data: list[EventOut]
    meta: PageMeta


class CurrentStepOut(CamelModel):
    id: str
    step_order: int
    name: str


class EventDetailOut(CamelModel):
    """L2 헤더. 목록 카드와 달리 현재 단계를 id까지 내려 Step 모달을 바로 연다."""

    id: str
    title: str
    status: EventStatus
    start_date: date | None
    end_date: date | None
    dday: int | None
    location: str | None
    headcount: int | None
    current_step: CurrentStepOut | None
    # EventOut과 같은 이유로 항상 null (accounting 기준으로 재정의 예정)
    payment: Any | None
    budget: Any | None


class DoneActionOut(CamelModel):
    id: str
    title: str
    status: ActionStatus


class RemainingActionOut(CamelModel):
    id: str
    title: str
    status: ActionStatus
    approve_needed: bool


class StepOut(CamelModel):
    id: str
    step_order: int
    # P2는 단계를 묶음(phase)별로 나눠 그리고, 카탈로그 코드로 단계를 구분한다.
    code: StepCode
    phase: StepPhase
    name: str
    actor: StepActor
    state: StepState
    starts_at: UtcDateTime | None
    deadline: UtcDateTime | None
    completed_count: int
    total_action_count: int
    completed_at: UtcDateTime | None
    done_actions: list[DoneActionOut]
    remaining_actions: list[RemainingActionOut]


class StepListResponse(CamelModel):
    data: list[StepOut]
    meta: None = None


# --- P1·P2 행사 계획 (#187) ----------------------------------------------


class EventCreateIn(CamelModel):
    club_id: str
    title: str | None = None


class EventCreateOut(CamelModel):
    id: str
    title: str
    status: EventStatus


class DraftOut(CamelModel):
    """임시 저장 목록 한 줄. saved_at이 null이면 아직 한 번도 저장 안 한 것이다."""

    id: str
    title: str
    event_type: EventType | None
    saved_at: UtcDateTime | None
    created_at: UtcDateTime


class DraftListResponse(CamelModel):
    data: list[DraftOut]
    meta: None = None


class PlanChatIn(CamelModel):
    message_id: str
    message: str
    base_revision: int


class PlanMessageOut(CamelModel):
    id: str
    seq: int
    role: Literal["USER", "ASSISTANT"]
    content: str


class PlanMessageListResponse(CamelModel):
    data: list[PlanMessageOut]
    meta: None = None


class PlannedStepOut(CamelModel):
    id: str
    step_order: int
    name: str
    actor: StepActor
    starts_at: UtcDateTime | None
    deadline: UtcDateTime | None


class PlannedStepListResponse(CamelModel):
    data: list[PlannedStepOut]
    meta: None = None


class PlanGenerateIn(CamelModel):
    base_revision: int
    use_current_conditions: bool = False


class ConditionMetaOut(CamelModel):
    status: Literal["tentative", "specified"]
    evidence_message_id: str
    evidence_quote: str


class PlanConditionsOut(CamelModel):
    title: str | None
    event_type: EventType | None
    headcount: int | None
    fee_per_person: int | None
    start_date: date | None
    end_date: date | None
    location: str | None
    budget_total: int | None


class PlanDraftOut(CamelModel):
    conditions: PlanConditionsOut
    condition_meta: dict[str, ConditionMetaOut]
    deferred_topics: list[str]


class GenerationReadinessOut(CamelModel):
    can_generate: bool
    reasons: list[str]


class GenerationResultOut(CamelModel):
    status: Literal["generated", "needs_clarification", "failed"]
    reason: str | None


class RecordLookupOut(CamelModel):
    status: Literal["available", "not_found", "failed", "rejected"]
    query: str | None
    reason: str | None


class PlanViewOut(CamelModel):
    reply: str | None
    draft: PlanDraftOut
    changed_fields: list[str]
    record_lookup: RecordLookupOut | None
    generation_readiness: GenerationReadinessOut
    generation_result: GenerationResultOut | None
    base_revision: int


class ExcludedStepOut(CamelModel):
    code: StepCode
    reason: str


class PlanSummaryOut(CamelModel):
    total_steps: int
    ai_steps: int
    approval_steps: int
    manual_steps: int


class PlanScreenOut(CamelModel):
    draft: PlanDraftOut
    warnings: list[str]
    excluded_steps: list[ExcludedStepOut]
    summary: PlanSummaryOut
    base_revision: int
    generation_readiness: GenerationReadinessOut | None = None
