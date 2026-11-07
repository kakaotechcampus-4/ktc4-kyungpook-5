"""채팅과 버튼의 검증 이후, 같은 생성 기능을 호출하고 성공 상태만 채택한다."""

from pydantic import Field, field_validator

from ....contracts import ChatTurn, ContractModel, NonBlankStr
from ....ports import PlanningProgressPort
from ..progress import notify, started, generation_finished, generation_step, generation_writing
from .step_reader import StepCodeReader
from ...retrieval.schemas import RecordFact
from ..agent.state import PlanningDraft
from ..schemas import CalendarDate
from .graph import run_plan_generation
from .offers import same_basis
from .readiness import BLOCK_MESSAGES, generation_blocks
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
    progress: PlanningProgressPort | None = None,
    operation_id: str | None = None,
) -> GenerationUpdate:
    """두 진입점의 공통 검증. 거절/실패 때 이전 성공 초안을 유실하지 않는다."""
    def clarify(reason):
        return GenerationUpdate(generation=state, result=PlanGenerationResult(status="needs_clarification", reason=reason))
    blocks = generation_blocks(request.basis_draft, state, use_current_conditions=use_current_conditions)
    if blocks:
        return clarify(BLOCK_MESSAGES[blocks[0]])
    previous = state.preview
    if previous and previous.trigger.source == request.trigger.source and previous.trigger.request_id == request.trigger.request_id:
        # 같은 성공 요청의 재전송은 모델을 다시 부르지 않는다. 변경된 조건에 ID를 재사용하지 않는다.
        if not same_basis(previous.basis_draft, request.basis_draft):
            return clarify("조건이 바뀌었어요. 새로운 생성 요청 ID로 다시 요청해 주세요.")
        return GenerationUpdate(generation=PlanningGenerationState(preview=previous),
                                result=PlanGenerationResult(status="generated", preview=previous))
    # 검증 차단·기존 결과 재사용을 지나 실제 생성할 때만 시작을 알린다.
    operation_id = operation_id or request.trigger.request_id
    await notify(progress, started(operation_id, generation=True))
    if progress is None:
        result = await generate(request.model_copy(deep=True))
    else:
        reader, writing = StepCodeReader(), False

        async def on_text(text):
            # 생성 모델의 계획 JSON 글자 조각이 올 때마다 불린다(검증 전 글).
            #   첫 조각            → generation_writing 한 번 (#388)
            #   단계 code 값이 끝남 → generation_step(위치, 코드, 고정 이름) (#389)
            # 글 자체는 밖으로 보내지 않는다. 알림 실패는 notify가 삼켜 생성을 멈추지 않는다.
            nonlocal writing
            if not writing:
                writing = True
                await notify(progress, generation_writing(operation_id))
            for index, code in reader.feed(text):
                await notify(progress, generation_step(operation_id, index, code))
        result = await generate(request.model_copy(deep=True), on_text=on_text)
    if result.status != "generated":
        await notify(progress, generation_finished(operation_id, result))
        return GenerationUpdate(generation=state, result=result)
    if result.preview.basis_draft != request.basis_draft or result.preview.trigger != request.trigger:
        result = PlanGenerationResult(status="failed",
            reason="생성 결과의 기준 조건이 요청과 달라요.", model_calls=result.model_calls)
        await notify(progress, generation_finished(operation_id, result))
        return GenerationUpdate(generation=state, result=result)
    await notify(progress, generation_finished(operation_id, result))
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
    progress: PlanningProgressPort | None = None,
) -> GenerationUpdate:
    # 클릭 자체가 명시적 요청이다. Agent의 의도 판단·권유 ID·HumanMessage를 만들지 않는다.
    shared = PlanGenerationInput(basis_draft=request.draft,
        trigger=ButtonGenerationTrigger(request_id=request.request_id), messages=request.messages,
        reference_date=request.reference_date, timezone=request.timezone, reference_facts=request.reference_facts)
    return await generate_with_context(shared, request.generation, generate=generate,
                                       use_current_conditions=request.use_current_conditions, progress=progress)
