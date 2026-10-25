"""P1 공개 경계: 복원 → 기존 실행 → 화면/보관 결과. 저장은 BE가 한다."""
from functools import partial

from ...contracts import (
    PlanningChatRequest, PlanningPreviewRequest, PlanningPublicResult,
    PlanningView, PlanningGenerationReadiness, PlanningResumeState, PlanningStatePayload,
)
from ...ports import RecordSearchPort
from .agent.graph import run_planning_agent_turn
from .agent.record_tool import search_past_events
from .agent.generation_tools import latest_reference_facts, plan_messages
from .generation.entrypoints import ButtonPlanGenerationRequest, run_button_plan_generation
from .generation.graph import run_plan_generation
from .generation.offers import same_basis
from .generation.readiness import generation_blocks
from .generation.schemas import PlanningGenerationState
from .state_codec import capture_turn_state, restore_history, to_agent_input


def build_result(request, state, *, reply=None, record_lookup=None, generation_result=None):
    draft = state.payload.basis_draft
    generation = state.payload.generation
    blocks = generation_blocks(draft, generation)
    return PlanningPublicResult(
        request_id=request.request_id, base_revision=request.base_revision,
        view=PlanningView(
            reply=reply, draft=draft,
            # 숫자는 답변에서 읽지 않는다. 처리 전후의 실제 값 차이만 알린다.
            changed_fields=tuple(field for field in type(draft.conditions).model_fields
                if getattr(request.draft.conditions, field) != getattr(draft.conditions, field)),
            record_lookup=record_lookup,
            generation_readiness=PlanningGenerationReadiness(can_generate=not blocks, reasons=blocks),
            generation_result=generation_result,
            preview_is_current=bool(generation.preview and same_basis(generation.preview.basis_draft, draft)
                                    and not generation.condition_change_pending),
        ), next_state=state,
    ).model_copy(deep=True)


async def chat(request: PlanningChatRequest, *, records: RecordSearchPort | None) -> PlanningPublicResult:
    # frozen 타입 안의 dict도 호출 중 바뀔 수 있으므로 실행용 스냅샷을 만든다.
    request = PlanningChatRequest.model_validate(request.model_dump(mode='json'))
    search = partial(search_past_events, club_id=request.club_id, port=records) if records is not None else None
    result = await run_planning_agent_turn(to_agent_input(request), search=search, generate=run_plan_generation)
    # 전체 호출 예외는 위로 전달한다. 정상 턴 안의 검색/생성 실패만 부분 결과로 반환한다.
    state = capture_turn_state(request, result)
    return build_result(request, state, reply=result.reply, record_lookup=result.record_lookup,
                        generation_result=result.generation_result)


async def generate_preview(request: PlanningPreviewRequest) -> PlanningPublicResult:
    request = PlanningPreviewRequest.model_validate(request.model_dump(mode='json'))
    history = restore_history(request.resume_state)
    generation = (request.resume_state.payload.generation if request.resume_state else PlanningGenerationState())
    update = await run_button_plan_generation(ButtonPlanGenerationRequest(
        request_id=request.request_id, draft=request.draft, generation=generation,
        messages=plan_messages(history), reference_facts=latest_reference_facts(history),
        reference_date=request.reference_date, timezone=request.timezone,
        use_current_conditions=request.use_current_conditions,
    ), generate=run_plan_generation)
    # 버튼은 새 발화가 아니다. 이력은 유지하고 생성 상태만 갱신한다.
    state = PlanningResumeState(
        club_id=request.club_id, event_id=request.event_id, conversation_id=request.conversation_id,
        payload=PlanningStatePayload(basis_draft=request.draft,
            history=request.resume_state.payload.history if request.resume_state else (),
            generation=update.generation),
    )
    return build_result(request, state, generation_result=update.result)
