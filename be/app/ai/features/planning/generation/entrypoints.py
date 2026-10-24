"""채팅과 버튼의 검증 이후, 같은 생성 기능을 호출하고 성공 상태만 채택한다."""

from pydantic import Field, field_validator

from ....contracts import ChatTurn, ContractModel, NonBlankStr
from ...retrieval.schemas import RecordFact
from ..agent.state import PlanningDraft
from ..schemas import CalendarDate
from .graph import run_plan_generation
from .offers import same_basis
from .schemas import (
    ButtonGenerationTrigger, PlanGenerationInput, PlanGenerationResult, PlanGenerator,
    PlanningGenerationState, valid_timezone,
)


class GenerationUpdate(ContractModel):
    generation: PlanningGenerationState
    result: PlanGenerationResult


async def generate_with_context(
    request: PlanGenerationInput, state: PlanningGenerationState, *, generate: PlanGenerator,
    use_current_conditions: bool = False,
) -> GenerationUpdate:
    """두 진입점의 공통 검증. 거절/실패 때 이전 성공 초안을 유실하지 않는다."""
    def clarify(reason):
        return GenerationUpdate(generation=state, result=PlanGenerationResult(status="needs_clarification", reason=reason))
    if request.basis_draft.conditions.event_type is None:
        return clarify("어떤 행사인지 먼저 정해 주세요.")
    if state.condition_change_pending and not use_current_conditions:
        return clarify("반영하지 못한 조건 변경이 있어요. 현재 남은 조건으로 만들지 먼저 확인해 주세요.")
    previous = state.preview
    if previous and previous.trigger.source == request.trigger.source and previous.trigger.request_id == request.trigger.request_id:
        # 같은 성공 요청의 재전송은 모델을 다시 부르지 않는다. 변경된 조건에 ID를 재사용하지 않는다.
        if not same_basis(previous.basis_draft, request.basis_draft):
            return clarify("조건이 바뀌었어요. 새로운 생성 요청 ID로 다시 요청해 주세요.")
        return GenerationUpdate(generation=PlanningGenerationState(preview=previous),
                                result=PlanGenerationResult(status="generated", preview=previous))
    result = await generate(request.model_copy(deep=True))
    if result.status != "generated":
        return GenerationUpdate(generation=state, result=result)
    if result.preview.basis_draft != request.basis_draft or result.preview.trigger != request.trigger:
        return GenerationUpdate(generation=state, result=PlanGenerationResult(status="failed",
            reason="생성 결과의 기준 조건이 요청과 달라요.", model_calls=result.model_calls))
    return GenerationUpdate(generation=PlanningGenerationState(preview=result.preview), result=result)


class ButtonPlanGenerationRequest(ContractModel):
    """내부 클릭 이벤트. FE 요청을 그대로 신뢰할 공개 API가 아니라 BE/로컬 어댑터의 입력이다."""
    request_id: NonBlankStr
    draft: PlanningDraft
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)
    messages: tuple[ChatTurn, ...] = ()
    reference_date: CalendarDate
    timezone: NonBlankStr = "Asia/Seoul"
    reference_facts: tuple[RecordFact, ...] = ()
    use_current_conditions: bool = False

    _timezone = field_validator("timezone")(valid_timezone)


async def run_button_plan_generation(
    request: ButtonPlanGenerationRequest, *, generate: PlanGenerator = run_plan_generation,
) -> GenerationUpdate:
    # 클릭 자체가 명시적 요청이다. Agent의 의도 판단·권유 ID·HumanMessage를 만들지 않는다.
    shared = PlanGenerationInput(basis_draft=request.draft,
        trigger=ButtonGenerationTrigger(request_id=request.request_id), messages=request.messages,
        reference_date=request.reference_date, timezone=request.timezone, reference_facts=request.reference_facts)
    return await generate_with_context(shared, request.generation, generate=generate,
                                       use_current_conditions=request.use_current_conditions)
