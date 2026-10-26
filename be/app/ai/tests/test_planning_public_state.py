"""#180: 저장 경계를 지나도 대화/Tool/생성 권유를 잃지 않는지 확인한다."""
import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError
from app.ai import PlanningChatRequest, PlanningConditions, PlanningDraft, PlanningResumeState, PlanningStateError, PlanningUserMessage, parse_resume_state
from app.ai.features.planning.agent.schemas import PlanningAgentTurnResult
from app.ai.features.planning.generation.schemas import GenerationOffer, PlanningGenerationState
from app.ai.features.planning.state_codec import capture_turn_state, to_agent_input


def request(**changes):
    data = dict(request_id='r1', club_id='c1', event_id='e1', conversation_id='chat1', base_revision=0,
                draft=PlanningDraft(conditions=PlanningConditions(fee_per_person=25000)),
                reference_date='2026-10-25', message=PlanningUserMessage(id='u1', content='3만 원이면 어때?'))
    data.update(changes)
    return PlanningChatRequest(**data)


def result(req, history=None):
    return PlanningAgentTurnResult(reply='3만 원으로 정할까요?', draft=req.draft,
        history=history if history is not None else (
            HumanMessage(id='u1', content='3만 원이면 어때?'),
            AIMessage(id='a1', content='', tool_calls=[dict(id='call1', name='example', args={'amount':30000})]),
            ToolMessage(id='t1', content='상담 참고 결과', tool_call_id='call1'),
            AIMessage(id='a2', content='3만 원으로 정할까요?', response_metadata={'provider_secret':'discard'}),
        ), executions=(), model_calls=2, limit_reached=False, prompt_version='test',
        generation=PlanningGenerationState(offer=GenerationOffer(id='offer1', status='pending',
            summary='초안을 만들까요?', basis_draft=req.draft)))


def test_json_roundtrip_retains_consultation_tools_and_offer():
    req = request()
    raw = capture_turn_state(req, result(req)).model_dump_json()
    assert 'provider_secret' not in raw
    followup = request(request_id='r2', base_revision=1, resume_state=parse_resume_state(raw),
        message=PlanningUserMessage(id='u2', content='일단 그렇게 잡자'))
    internal = to_agent_input(followup)
    assert internal.current_message.text == '일단 그렇게 잡자'
    assert internal.draft.conditions.fee_per_person == 25000
    assert internal.history[-1].content == '3만 원으로 정할까요?'
    assert internal.history[1].tool_calls[0]['args'] == {'amount':30000}
    assert internal.history[2].tool_call_id == 'call1'
    assert internal.generation.offer.id == 'offer1'


@pytest.mark.parametrize('field', ['event_id','club_id','conversation_id'])
def test_cross_scope_rejected(field):
    with pytest.raises(ValidationError, match='다른 행사'):
        request(resume_state=capture_turn_state(request(), result(request())), **{field:'other'})


def test_external_draft_change_not_silently_overwritten():
    with pytest.raises(ValidationError, match='동기화'):
        request(resume_state=capture_turn_state(request(), result(request())),
            draft=PlanningDraft(conditions=PlanningConditions(fee_per_person=30000)))


@pytest.mark.parametrize('version', [2, True, '1', 1.0])
def test_unsupported_version(version):
    raw = json.loads(capture_turn_state(request(), result(request())).model_dump_json())
    raw['schema_version'] = version
    with pytest.raises(PlanningStateError) as exc:
        parse_resume_state(json.dumps(raw))
    assert exc.value.code == 'unsupported_version'


@pytest.mark.parametrize('raw', ['null','{}','not-json'])
def test_invalid_json_state(raw):
    with pytest.raises(PlanningStateError) as exc:
        parse_resume_state(raw)
    assert exc.value.code == 'invalid_state'


def test_missing_tool_result_rejected():
    raw = json.loads(capture_turn_state(request(), result(request())).model_dump_json())
    del raw['payload']['history'][2]
    with pytest.raises(PlanningStateError) as exc:
        parse_resume_state(json.dumps(raw))
    assert exc.value.code == 'invalid_state'


def test_duplicate_current_message_rejected():
    with pytest.raises(ValidationError, match='이미 이력'):
        request(resume_state=capture_turn_state(request(), result(request())))


@pytest.mark.parametrize('length', [60, 61])
def test_history_boundary(length):
    req = request()
    history = tuple(HumanMessage(id=f'h{i}', content='예시') for i in range(length))
    if length == 61:
        with pytest.raises(PlanningStateError) as exc:
            capture_turn_state(req, result(req, history))
        assert exc.value.code == 'history_limit'
    else:
        state = capture_turn_state(req, result(req, history))
        assert len(to_agent_input(request(resume_state=state)).history) == 60


def test_state_is_detached_from_result():
    req = request()
    turn = result(req)
    state = capture_turn_state(req, turn)
    turn.history[1].tool_calls[0]['args']['amount'] = 999
    assert state.payload.history[1].tool_calls[0].args['amount'] == 30000
    assert PlanningResumeState.model_validate_json(state.model_dump_json()) == state


def test_real_graph_can_continue_after_json_restore():
    """모델 선택은 고정하고 실제 Graph/조건 Tool/저장 경계를 함께 통과한다."""
    import asyncio
    from app.ai.features.planning.agent.graph import run_planning_agent_turn
    from app.ai.features.planning.agent.nodes import TOOL_NAME

    async def scenario():
        req = request()
        async def consultation(messages, *, allow_tools):
            return AIMessage(content='3만 원을 기준으로 검토할 수 있어요.')
        first = await run_planning_agent_turn(to_agent_input(req), invoke=consultation)
        state = parse_resume_state(capture_turn_state(req, first).model_dump_json())
        next_req = request(request_id='r2', resume_state=state,
            message=PlanningUserMessage(id='u2', content='일단 그렇게 잡자'))
        calls = 0
        async def acceptance(messages, *, allow_tools):
            nonlocal calls
            calls += 1
            if calls == 1:
                assert any(m.content == '3만 원을 기준으로 검토할 수 있어요.' for m in messages)
                return AIMessage(content='', tool_calls=[dict(id='change1', name=TOOL_NAME, args={
                    'changes':[dict(op='SET', change=dict(field='fee_per_person', value=30000),
                        status='tentative', evidence=dict(message_id='u2', quote='일단 그렇게 잡자'))]})])
            return AIMessage(content='일단 3만 원으로 반영했어요.')
        second = await run_planning_agent_turn(to_agent_input(next_req), invoke=acceptance)
        final = parse_resume_state(capture_turn_state(next_req, second).model_dump_json())
        assert final.payload.basis_draft.conditions.fee_per_person == 30000
        assert final.payload.basis_draft.condition_meta['fee_per_person'].status == 'tentative'
        assert len(final.payload.history) == 6
    asyncio.run(scenario())


def test_public_result_rejects_different_display_and_saved_conditions():
    from app.ai import PlanningPublicResult, PlanningView, PlanningGenerationReadiness
    with pytest.raises(ValidationError, match='화면 조건'):
        PlanningPublicResult(request_id='r1', base_revision=0,
            view=PlanningView(draft=PlanningDraft(),
                generation_readiness=PlanningGenerationReadiness(can_generate=False, reasons=('event_type_missing',))),
            next_state=capture_turn_state(request(), result(request())))


def test_button_request_has_no_message_and_defaults_to_no_override():
    from app.ai import PlanningPreviewRequest
    fields = request().model_dump(exclude={'message'})
    button = PlanningPreviewRequest(**fields)
    assert not button.use_current_conditions
    with pytest.raises(ValidationError):
        PlanningPreviewRequest(**fields, message={'id':'fake', 'content':'만들어줘'})
