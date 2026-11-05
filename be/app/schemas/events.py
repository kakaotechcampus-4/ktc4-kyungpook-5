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
    PlanReviewStatus,
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
    """L1 행사 카드. 계획 중(PLANNING)에는 단계 진행 전이라 currentStepName이 null이고 stepProgress가 모두 TODO다(#336)."""

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


class EventStartOut(CamelModel):
    """계획 확정(행사 시작) 결과. FE 명세 v1의 :confirm을 #213 요청대로 /start로 연다."""

    id: str
    status: EventStatus
    title: str
    start_date: date | None

class EventCancelTaskOut(CamelModel):
    id: str
    task_order: int
    name: str
    description: str
    message: str | None
    state: Literal["DONE", "CURRENT", "TODO"]
    completed_at: UtcDateTime | None

class EventCancelTaskListResponse(CamelModel):
    data: list[EventCancelTaskOut]


class CurrentStepOut(CamelModel):
    id: str
    step_order: int
    name: str


class EventDetailOut(CamelModel):
    """L2 헤더. 목록 카드와 달리 현재 단계를 id까지 내려 Step 모달을 바로 연다. 계획 중(PLANNING)에는 currentStep이 null이다(#336)."""

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
    """L2 단계. state는 운영 시작 뒤에만 CURRENT가 생긴다. 계획 중(PLANNING)에는 모두 TODO다(#336)."""

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
    version: int


class PlannedStepOut(CamelModel):
    id: str
    # 고정 카탈로그 코드(#69). FE가 이름 문자열로 단계를 되찾지 않게 함께 내려보낸다.
    code: StepCode
    step_order: int
    version: int
    name: str
    actor: StepActor
    starts_at: UtcDateTime | None
    deadline: UtcDateTime | None
    # 세부 수정 가능 여부 (#106 ③). 끝난 단계는 고칠 수 없다.
    editable: bool
    actions: list[PlannedStepActionOut]


class PlanStepsUpdateIn(CamelModel):
    """단계 구성 저장. expectedRevision은 최근 계획 대화 revision이다."""

    codes: list[StepCode]
    expected_revision: int = Field(ge=0)


class PlanStepsSnapshotOut(CamelModel):
    """단계 구성과 그 구성을 읽은 시점의 버전."""

    base_revision: int
    # 계획 편집 버전 (#177). 저장 뒤 값과 비교해 실제로 바뀌었을 때만 검토를 요청한다.
    plan_revision: int
    steps: list[PlannedStepOut]


class StepUpdateIn(CamelModel):
    """단계 일정 수정 (#106 ④). 보낸 밭만 바뀐다."""

    expected_version: int = Field(ge=1)
    starts_at: UtcDateTime | None = None
    deadline: UtcDateTime | None = None


class ActionUpdateIn(CamelModel):
    """Action 세부 수정 (#106 ④). 보낸 밭만 바뀐다."""

    expected_version: int = Field(ge=1)
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


class RecordEvidenceLocationOut(CamelModel):
    label: str


class RecordEvidenceSourceOut(CamelModel):
    record_id: str
    file_name: str
    location: RecordEvidenceLocationOut


class RecordEvidenceFactOut(CamelModel):
    content: str
    sources: list[RecordEvidenceSourceOut] = Field(min_length=1)


class RecordEvidenceConflictOut(CamelModel):
    description: str
    values: list[RecordEvidenceFactOut] = Field(min_length=2)


class RecordEvidenceOut(CamelModel):
    facts: list[RecordEvidenceFactOut]
    not_found: list[str]
    conflicts: list[RecordEvidenceConflictOut]


class RecordLookupOut(CamelModel):
    status: Literal["available", "not_found", "failed", "rejected"]
    query: str | None
    reason: str | None
    # 옛 멱등 응답에는 상세 결과가 없다. null은 근거 없음으로 바꾸지 않는다.
    result: RecordEvidenceOut | None = None


class RecordLookupHistoryOut(CamelModel):
    revision: int
    lookup: RecordLookupOut


class HistoryUsageOut(CamelModel):
    """대화 이력 사용량 (#194). Tool 메시지까지 센 값이라 남은 대화 횟수가 아니다."""

    message_count: int
    max_messages: int
    near_limit: bool


class PlanProgressOut(CamelModel):
    """SSE progress 이벤트(#284). 저장되지 않는 임시 작업 상태이며 DB 저장 완료가 아니다.

    같은 operationId의 running 줄을 completed/failed 줄로 바꿔 표시한다.
    """

    operation_id: str
    kind: Literal[
        "condition_started", "condition_applied", "search_started", "search_finished",
        "generation_started", "generation_finished",
    ]
    # skipped는 같은 operationId의 running 줄을 지우라는 뜻이다(조건 거절·같은 값, #290).
    # empty는 정상으로 끝났지만 찾은 것이 없다는 뜻이다(기록 검색 자료 없음, #300).
    status: Literal["running", "completed", "failed", "skipped", "empty"]
    text: str
    condition_draft: PlanDraftOut | None = None


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


class PlanRequestOut(CamelModel):
    """요청 키 하나의 처리 결과 (#342). 응답 도중 연결이 끊긴 FE가 조회한다.

    completed: 저장까지 끝남. result는 그 요청이 받았어야 할 PlanViewOut 그대로다.
    processing: 아직 처리 중. 잠시 뒤 다시 조회한다.
    not_saved: 저장되지 않았다. 같은 내용을 새 요청으로 다시 보내도 된다.
    """

    status: Literal["completed", "processing", "not_saved"]
    result: PlanViewOut | None = None


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


class PlanReviewIn(CamelModel):
    """계획 수정 후 AI 검토 요청 (#177). 화면이 본 버전과 다르면 409."""

    expected_revision: int = Field(ge=0)


class PlanReviewItemOut(CamelModel):
    step_codes: list[StepCode]
    # 카탈로그 고정 이름. AI 출력에 이름을 맡기지 않는다.
    step_names: list[str]
    kind: str
    message: str
    suggestion: str | None


class PlanReviewOut(CamelModel):
    """REVIEWING이 90초를 넘으면 status=FAILED, errorCode=REVIEW_TIMEOUT으로 내보낸다."""

    status: PlanReviewStatus
    generated_revision: int
    reviewed_revision: int | None
    outcome: str | None
    items: list[PlanReviewItemOut]
    error_code: str | None


class PlanScreenOut(CamelModel):
    draft: PlanDraftOut
    warnings: list[str]
    excluded_steps: list[ExcludedStepOut]
    summary: PlanSummaryOut
    history_usage: HistoryUsageOut | None = None
    base_revision: int
    generation_readiness: GenerationReadinessOut | None = None
    last_record_lookup: RecordLookupOut | None = None
    record_lookup_history: list[RecordLookupHistoryOut] = Field(default_factory=list)
    # 계획 편집 버전 (#177). review.reviewedRevision과 비교해 검토가 지금 계획 기준인지 본다.
    plan_revision: int
    # 초안 생성 전이면 null.
    review: PlanReviewOut | None
