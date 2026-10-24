"""채팅의 생성 요청을 검증한 뒤 공통 생성 처리로 연결한다."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from ....contracts import ChatTurn, ContractModel, NonBlankStr
from ..generation.entrypoints import GenerationUpdate, generate_with_context
from ..generation.offers import same_basis, valid_evidence
from ..generation.schemas import (
    ChatGenerationTrigger, PlanGenerationInput, PlanGenerationResult, PlanGenerator, PlanningGenerationState,
)
from ..schemas import MessageEvidence, PlanningConditions
from .record_tool import RecordLookupResult
from .schemas import PlanningAgentTurnInput
from .state import PlanningDraft
from .tools import ConditionUpdateResult


class GenerateEventPlanInput(ContractModel):
    quote: NonBlankStr
    offer_id: str | None = None
    use_current_conditions: bool = False


def condition_generation_state(
    state: PlanningGenerationState, result: ConditionUpdateResult, raw_arguments: dict,
) -> PlanningGenerationState:
    """거절된 변경은 다른 필드를 고쳤다고 해제하지 않는다. 같은 필드의 성공으로 해소한다."""
    fields = set()
    changes = raw_arguments.get("changes", [])
    if isinstance(changes, (list, tuple)):
        for change in changes:
            if isinstance(change, dict):
                value = change.get("change")
                field = value.get("field") if isinstance(value, dict) else change.get("field")
                if isinstance(field, str) and field in PlanningConditions.model_fields:
                    fields.add(field)
    if result.status == "rejected":
        pending = set(state.pending_condition_fields) | fields
        blocked = True
    else:
        pending = set(state.pending_condition_fields) - fields
        blocked = bool(pending) or (state.condition_change_pending and not state.pending_condition_fields)
    return PlanningGenerationState(offer=state.offer, preview=state.preview,
        condition_change_pending=blocked, pending_condition_fields=tuple(sorted(pending)))


def latest_reference_facts(messages):
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == "search_past_events":
            try:
                lookup = RecordLookupResult.model_validate_json(message.content)
            except (ValidationError, ValueError, TypeError):
                return ()
            # 실패/없음을 옛 성공 자료로 바꾸지 않는다. 충돌한 값은 단일 사실로 전달하지 않는다.
            return lookup.result.facts if lookup.status == "available" else ()
    return ()


def plan_messages(messages) -> tuple[ChatTurn, ...]:
    """두 진입점이 같은 텍스트 문맥을 만든다. Tool·SDK 메타정보는 생성 입력에 넣지 않는다."""
    return tuple(ChatTurn(role="USER" if isinstance(m, HumanMessage) else "ASSISTANT", content=m.text)
                 for m in messages if isinstance(m, (HumanMessage, AIMessage)) and m.text.strip())


async def generate_event_plan(
    arguments: GenerateEventPlanInput, *, request: PlanningAgentTurnInput, draft: PlanningDraft,
    state: PlanningGenerationState, messages, generate: PlanGenerator,
) -> GenerationUpdate:
    def clarify(reason):
        return GenerationUpdate(generation=state,
            result=PlanGenerationResult(status="needs_clarification", reason=reason))
    # 이번 메시지 ID는 모델이 복사하지 않는다. 현재 요청에 바인딩해 원문만 검사한다.
    evidence = MessageEvidence(message_id=request.current_message.id, quote=arguments.quote)
    if not valid_evidence(evidence, request.current_message):
        return clarify("생성에는 이번 사용자 발화의 실제 요청·수락 문구가 필요해요.")
    if arguments.offer_id is not None:
        offer = state.offer
        if offer is None or offer.id != arguments.offer_id or offer.status != "pending":
            return clarify("지금 수락할 수 있는 생성 권유인지 다시 확인해 주세요.")
        if not same_basis(offer.basis_draft, draft):
            return clarify("권유한 뒤 행사 조건이 바뀌었어요. 최신 조건으로 만들지 확인해 주세요.")
    # 버튼과 달리 여기까지는 LLM이 요청을 해석한 채팅 경로다. 실제 생성은 같은 함수를 쓴다.
    shared = PlanGenerationInput(basis_draft=draft,
        trigger=ChatGenerationTrigger(request_id=request.current_message.id, quote=arguments.quote),
        messages=plan_messages(messages),
        reference_date=request.reference_date, timezone=request.timezone,
        reference_facts=latest_reference_facts(messages))
    return await generate_with_context(shared, state, generate=generate,
                                       use_current_conditions=arguments.use_current_conditions)
