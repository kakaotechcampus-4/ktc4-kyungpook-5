"""행사 도메인 요청·응답 스키마.

내부(모델·서비스)는 snake_case, API 경계는 camelCase다. 변환은 CamelModel이 맡고
서비스·모델 쪽은 이름을 바꾸지 않는다.

enum은 core/enums.py의 StrEnum을 그대로 쓴다. 값이 곧 API 코드라 변환이 필요 없다.
"""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_serializer

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


class ActionPayloadOut(CamelModel):
    """Action 유형별 설정값 (#106 ①).

    키는 ActionType마다 다르고, 해당 없는 키는 내려보내지 않는다 — FE는 없는
    키의 입력 밭을 그리지 않는다. CONFIRMATION의 선택지는 ActionOut의
    options·allow_manual로 평탄화해 내려보내므로 여기 담지 않는다.
    """

    model_config = CamelModel.model_config | {"extra": "ignore"}

    # NOTICE · EXTERNAL_SEND
    channel: str | None = None
    audience: str | None = None
    # EXTERNAL_SEND
    send_timing: str | None = None
    # CONTRACT
    vendor: str | None = None
    cancel_terms: str | None = None
    # TRANSFER
    account: str | None = None
    # EXPENSE
    receipt_required: bool | None = None
    approval_mode: Literal["BATCH", "EACH"] | None = None

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler):
        """해당 없는 키는 아예 빼고 내려보낸다 (#106 ①).

        FE는 키가 없으면 그 입력 밭을 그리지 않는다. null로 내려보내면
        "값이 비었다"와 "이 유형에는 없는 설정이다"를 구분할 수 없다.
        """
        return {key: value for key, value in handler(self).items() if value is not None}


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
    # 유형별 설정값 (#106 ①). 세부 수정 모달이 어떤 밭을 그릴지 이걸로 정한다.
    # CONFIRMATION은 위 options·allow_manual로 이미 펼쳤으므로 여기서는 비운다.
    payload: ActionPayloadOut | None
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


class PlannedStepActionOut(CamelModel):
    """계획 화면이 쓰는 Action 요약 (#106).

    세부 수정 모달이 필요한 것만 담는다. 승인 흐름에 쓰는 ActionOut과 달리
    content·resolver·canApprove는 넣지 않는다 — 계획 중에는 아직 쓰이지 않는다.
    """

    id: str
    type: ActionType
    title: str
    subtitle: str | None
    amount: int | None
    due_date: date | None
    payload: ActionPayloadOut | None
    editable: bool


class PlannedStepOut(CamelModel):
    id: str
    # 고정 카탈로그 코드(#69). FE가 이름 문자열로 단계를 되찾지 않게 함께 내려보낸다.
    code: StepCode
    step_order: int
    name: str
    actor: StepActor
    starts_at: UtcDateTime | None
    deadline: UtcDateTime | None
    # 세부 수정 가능 여부 (#106 ③). 끝난 단계는 고칠 수 없다.
    editable: bool
    actions: list[PlannedStepActionOut]


class PlanStepsUpdateIn(CamelModel):
    """단계 구성 저장 (#213 3단계).

    배열 순서가 곧 묶음 안의 순서다. 일정은 PATCH /steps/{id}가 맡으므로
    여기서는 받지 않는다 — 한 번에 두 가지를 바꾸면 무엇이 실패했는지 흐려진다.
    """

    codes: list[StepCode]


class EventStatusOut(CamelModel):
    id: str
    status: EventStatus


class StepUpdateIn(CamelModel):
    """단계 일정 수정 (#106 ④). 보낸 밭만 바뀐다."""

    starts_at: UtcDateTime | None = None
    deadline: UtcDateTime | None = None


class ActionUpdateIn(CamelModel):
    """Action 세부 수정 (#106 ④). 보낸 밭만 바뀐다.

    payload는 통째로 바꾸지 않고 보낸 키만 덮는다 — 모달이 그리지 않는 키
    (예: CONFIRMATION의 선택지)를 지우면 안 된다.
    """

    title: str | None = None
    subtitle: str | None = None
    amount: int | None = None
    due_date: date | None = None
    payload: ActionPayloadOut | None = None


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
