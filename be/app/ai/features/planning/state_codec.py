"""SDK 메시지 ↔ JSON 계약 변환. DB와 모델 호출 없이 상태를 보관/복원한다."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from ...errors import PlanningStateError

from ...contracts import (
    MAX_PLANNING_HISTORY, PlanningChatRequest, PlanningRequestContext, PlanningResumeState,
    PlanningStatePayload, PlanningStoredMessage, PlanningStoredToolCall,
)
from .agent.schemas import PlanningAgentTurnInput, PlanningAgentTurnResult, validate_planning_history
from .schemas import PlanningMessage


# BE가 저장했던 JSON 복원
def parse_resume_state(raw: str) -> PlanningResumeState:
    """저장 JSON의 미지원 버전과 손상을 구분한다. 임의 초기화하지 않는다."""
    import json
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise PlanningStateError('invalid_state', '계획 상태 JSON을 읽을 수 없습니다') from error
    if isinstance(data, dict) and 'schema_version' in data:
        version = data['schema_version']
        if type(version) is not int or version != 1:
            raise PlanningStateError('unsupported_version', '지원하지 않는 계획 상태 버전입니다')
    else:
        raise PlanningStateError('invalid_state', '계획 상태 버전이 없습니다')
    try:
        return PlanningResumeState.model_validate(data)
    except ValidationError as error:
        raise PlanningStateError('invalid_state', '계획 상태 구조를 복원할 수 없습니다') from error


def restore_history(state: PlanningResumeState | None):
    if state is None:
        return ()
    messages = []
    for item in state.payload.history:
        common = dict(content=item.content, id=item.id, name=item.name)
        if item.role == 'user':
            messages.append(HumanMessage(**common))
        elif item.role == 'assistant':
            calls = [dict(id=c.id, name=c.name, args=c.args, type='tool_call') for c in item.tool_calls]
            messages.append(AIMessage(**common, tool_calls=calls))
        else:
            messages.append(ToolMessage(**common, tool_call_id=item.tool_call_id, status=item.tool_status))
    # 복원한 메시지도 기존 이력 검증을 통과해야 한다.
    validate_planning_history(tuple(messages))
    return tuple(messages)


def to_agent_input(request: PlanningChatRequest) -> PlanningAgentTurnInput:
    """BE 입력을 기존 Agent 입력으로 바꾸고 저장된 생성 권유도 복원한다."""
    from .generation.schemas import PlanningGenerationState
    return PlanningAgentTurnInput(
        draft=request.draft.model_copy(deep=True),
        current_message=PlanningMessage(id=request.message.id, role='user', text=request.message.content),
        history=restore_history(request.resume_state), reference_date=request.reference_date,
        timezone=request.timezone,
        generation=(request.resume_state.payload.generation.model_copy(deep=True)
                    if request.resume_state else PlanningGenerationState()),
    )


# 대화와 Tool 이력을 저장 가능한 상태로 변환 (BE가 보관)
def capture_turn_state(request: PlanningRequestContext, result: PlanningAgentTurnResult) -> PlanningResumeState:
    """다음 입력에서 복원할 수 없는 결과를 정상 저장 상태로 반환하지 않는다."""
    if len(result.history) > MAX_PLANNING_HISTORY:
        raise PlanningStateError('history_limit', '대화 이력 한도에 도달했습니다. 요약 정책 연결이 필요합니다')
    validate_planning_history(result.history)
    stored = []
    for message in result.history:
        common = dict(id=message.id, content=message.content, name=message.name)
        if isinstance(message, HumanMessage):
            stored.append(PlanningStoredMessage(role='user', **common))
        elif isinstance(message, AIMessage):
            stored.append(PlanningStoredMessage(role='assistant', **common, tool_calls=tuple(
                PlanningStoredToolCall(id=c['id'], name=c['name'], args=c['args']) for c in message.tool_calls
            )))
        else:
            stored.append(PlanningStoredMessage(role='tool', **common,
                tool_call_id=message.tool_call_id, tool_status=message.status))
    # 응답 사용량/공급자 메타데이터 대신 다음 모델 호출에 필요한 내용만 저장한다.
    return PlanningResumeState(
        club_id=request.club_id, event_id=request.event_id, conversation_id=request.conversation_id,
        payload=PlanningStatePayload(basis_draft=result.draft, history=tuple(stored), generation=result.generation),
    ).model_copy(deep=True)
