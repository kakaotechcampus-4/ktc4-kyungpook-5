"""행사 도메인 요청·응답 스키마.

내부(모델·서비스)는 snake_case, API 경계는 camelCase다. 변환은 CamelModel이 맡고
서비스·모델 쪽은 이름을 바꾸지 않는다.

enum은 core/enums.py의 StrEnum을 그대로 쓴다. 값이 곧 API 코드라 변환이 필요 없다.
"""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints

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
    # 확인 요청에서 고른 선택지 key(또는 MANUAL)와 직접 입력한 답. 처리 전에는 null.
    resolved_choice: str | None
    manual_value: str | None
    # 처리·수정 요청의 expectedVersion으로 그대로 보낸다 (#41 낙관적 잠금).
    version: int


class ActionListResponse(CamelModel):
    data: list[ActionOut]
    meta: PageMeta


# --- 행동 처리 (#41) ------------------------------------------------------


class ActionVersionIn(CamelModel):
    """승인·실행 완료 요청. 클라이언트가 본 행동의 version을 보낸다."""

    expected_version: int = Field(ge=1)


class ActionDenyIn(ActionVersionIn):
    # 선택 입력. 결정 검토 모달의 입력 제한과 같다.
    reason: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=500)
    ] = None


class ActionResolveIn(ActionVersionIn):
    # options[].key 중 하나, 또는 MANUAL(직접 처리)
    choice: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    # choice=MANUAL일 때 사용자가 직접 입력한 답. 답변 모달의 입력 제한과 같다.
    manual_value: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=200)
    ] = None


class StepCompleteOut(CamelModel):
    """단계 완료 처리 결과. 미처리 행동이 남아 있으면 FE가 확인 문구를 띄운다."""

    id: str
    completed_at: UtcDateTime
    # 행동이 모두 끝나 자동으로 완료된 단계는 null이다.
    completed_by: ResolvedBy | None
    pending_action_count: int


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


class EventConfirmOut(CamelModel):
    """계획 확정 결과 (FE 명세 v1 :confirm)."""

    id: str
    status: EventStatus
    title: str
    start_date: date | None


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
    # AI 계약(PlanningUserMessage)과 같은 제약. 여기서 막지 않으면 AI 요청을 만들 때
    # 검증 오류가 나 500이 된다.
    message_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    base_revision: int = Field(ge=0)


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
    base_revision: int = Field(ge=0)
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


class HistoryUsageOut(CamelModel):
    """대화 이력 사용량 (#194). Tool 메시지까지 센 값이라 남은 대화 횟수가 아니다."""

    message_count: int
    max_messages: int
    near_limit: bool


class PlanViewOut(CamelModel):
    reply: str | None
    draft: PlanDraftOut
    changed_fields: list[str]
    record_lookup: RecordLookupOut | None
    generation_readiness: GenerationReadinessOut
    generation_result: GenerationResultOut | None
    # 예전에 저장한 멱등 응답에는 없어서 기본값을 둔다.
    history_usage: HistoryUsageOut | None = None
    base_revision: int


class ExcludedStepOut(CamelModel):
    code: StepCode
    # 카탈로그 고정 이름 (#198). 그 전에 저장한 계획에는 없어 null이다.
    name: str | None = None
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
    history_usage: HistoryUsageOut | None = None
    base_revision: int
    generation_readiness: GenerationReadinessOut | None = None
