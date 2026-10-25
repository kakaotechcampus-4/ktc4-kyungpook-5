"""P1 공개 데이터 계약 초안 (#180). 실행 facade는 후속 작업에서 연결한다.

기존 내부 타입의 검증을 재사용하되 BE는 app.ai에서만 이름을 가져온다.
저장 상태에는 LangChain 객체나 공급자 응답 메타데이터를 넣지 않는다.
"""
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from .contracts import ContractModel, NonBlankStr
from .features.planning.agent.state import PlanningDraft
from .features.planning.agent.record_tool import RecordLookupResult
from .features.planning.generation.schemas import (
    PlanGenerationResult, PlanningGenerationState, valid_timezone,
)
from .features.planning.schemas import CalendarDate, ConditionField, PlanningConditions

MAX_PLANNING_HISTORY = 60


class PlanningStateError(ValueError):
    """복원 실패를 빈 대화로 숨기지 않도록 구분하는 공개 오류."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class PlanningStoredToolCall(ContractModel):
    id: NonBlankStr
    name: NonBlankStr
    args: dict[str, JsonValue]


class PlanningStoredMessage(ContractModel):
    role: Literal['user', 'assistant', 'tool']
    id: NonBlankStr | None = None
    content: str | list[str | dict[str, JsonValue]]
    tool_calls: tuple[PlanningStoredToolCall, ...] = ()
    tool_call_id: NonBlankStr | None = None
    tool_status: Literal['success', 'error'] | None = None

    @model_validator(mode='after')
    def validate_role(self) -> Self:
        if self.role != 'assistant' and self.tool_calls:
            raise ValueError('Tool 호출은 assistant 메시지에만 가능합니다')
        if self.role == 'tool':
            if self.tool_call_id is None or self.tool_status is None:
                raise ValueError('Tool 결과에는 호출 ID와 상태가 필요합니다')
        elif self.tool_call_id is not None or self.tool_status is not None:
            raise ValueError('Tool 결과 필드는 tool 메시지에만 가능합니다')
        return self


class PlanningStatePayload(ContractModel):
    basis_draft: PlanningDraft
    history: tuple[PlanningStoredMessage, ...] = Field(default=(), max_length=MAX_PLANNING_HISTORY)
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)

    @model_validator(mode='after')
    def validate_pairs(self) -> Self:
        # AI의 호출과 Tool 결과가 하나의 묶음이어야 다음 모델 호출이 가능하다.
        pending: set[str] = set()
        seen: set[str] = set()
        message_ids: set[str] = set()
        for message in self.history:
            if message.id is not None:
                if message.id in message_ids:
                    raise ValueError('메시지 ID가 중복되었습니다')
                message_ids.add(message.id)
            if message.role == 'tool':
                if message.tool_call_id not in pending:
                    raise ValueError('대응하는 Tool 호출이 없습니다')
                pending.remove(message.tool_call_id)
                continue
            if pending:
                raise ValueError('Tool 호출 뒤 실행 결과가 필요합니다')
            for call in message.tool_calls:
                if call.id in seen:
                    raise ValueError('Tool 호출 ID가 중복되었습니다')
                seen.add(call.id)
                pending.add(call.id)
        if pending:
            raise ValueError('실행 결과가 없는 Tool 호출입니다')
        return self


class PlanningResumeState(ContractModel):
    schema_version: Literal[1] = 1
    club_id: NonBlankStr
    event_id: NonBlankStr
    conversation_id: NonBlankStr
    payload: PlanningStatePayload

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise PlanningStateError('unsupported_version', '지원하지 않는 계획 상태 버전입니다')
        return value


class PlanningUserMessage(ContractModel):
    id: NonBlankStr
    content: Annotated[NonBlankStr, Field(max_length=4000)]


class PlanningRequestContext(ContractModel):
    request_id: NonBlankStr
    club_id: NonBlankStr
    event_id: NonBlankStr
    conversation_id: NonBlankStr
    base_revision: Annotated[int, Field(strict=True, ge=0)]
    draft: PlanningDraft
    resume_state: PlanningResumeState | None = None
    reference_date: CalendarDate
    timezone: NonBlankStr = 'Asia/Seoul'

    _timezone = field_validator('timezone')(valid_timezone)

    @model_validator(mode='after')
    def validate_resume(self) -> Self:
        state = self.resume_state
        if state is not None:
            if (self.club_id, self.event_id, self.conversation_id) != (
                state.club_id, state.event_id, state.conversation_id,
            ):
                raise PlanningStateError('scope_mismatch', '다른 행사 또는 대화의 상태입니다')
            if self.draft != state.payload.basis_draft:
                raise PlanningStateError('draft_mismatch', '조건과 대화 상태의 동기화가 필요합니다')
        return self


class PlanningChatRequest(PlanningRequestContext):
    message: PlanningUserMessage

    @model_validator(mode='after')
    def validate_new_message(self) -> Self:
        if self.resume_state and any(
            m.id == self.message.id for m in self.resume_state.payload.history
        ):
            raise ValueError('이번 메시지가 이미 이력에 있습니다')
        return self


class PlanningPreviewRequest(PlanningRequestContext):
    use_current_conditions: bool = False


class PlanningGenerationReadiness(ContractModel):
    can_generate: bool
    reasons: tuple[Literal['event_type_missing', 'condition_change_pending'], ...] = ()

    @model_validator(mode='after')
    def validate_reasons(self) -> Self:
        if self.can_generate == bool(self.reasons):
            raise ValueError('생성 가능 여부와 차단 사유가 일치하지 않습니다')
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError('차단 사유가 중복되었습니다')
        return self


class PlanningView(ContractModel):
    reply: NonBlankStr | None = None
    draft: PlanningDraft
    changed_fields: tuple[ConditionField, ...] = ()
    record_lookup: RecordLookupResult | None = None
    generation_readiness: PlanningGenerationReadiness
    generation_result: PlanGenerationResult | None = None
    preview_is_current: bool = False


class PlanningPublicResult(ContractModel):
    request_id: NonBlankStr
    base_revision: Annotated[int, Field(strict=True, ge=0)]
    view: PlanningView
    next_state: PlanningResumeState

    @model_validator(mode='after')
    def validate_snapshot(self) -> Self:
        if self.view.draft != self.next_state.payload.basis_draft:
            raise ValueError('화면 조건과 보관 상태의 조건이 다릅니다')
        return self
