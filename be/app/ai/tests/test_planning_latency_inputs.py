"""#196: 측정 요청이 같은 출발 상태를 사용하고 생성 결과를 재사용하지 않는지 확인한다."""

import json
from functools import partial

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.ai import (PlanningChatRequest, PlanningPreviewRequest, chat_planning, generate_planning_preview,
                    planning_generation_readiness)
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent.nodes import GENERATE_TOOL_NAME
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request, request_hashes, schedule, LatencyFixture
from app.ai.tests.test_plan_generation_graph import Model
from app.ai.tests.test_planning_public_workflow import run, scripted, tool


def test_fixture_restores_a_real_offer_and_four_independent_requests():
    fixture = load_fixture()
    before = fixture.model_dump_json()
    state = fixture.resume_state
    assert set(state.payload.basis_draft.deferred_topics) == {"dates", "location"}
    assert planning_generation_readiness(state.payload.basis_draft, resume_state=state).can_generate
    requests = [make_request(fixture, case, f's1-{case.id}') for case in fixture.cases]
    assert all(isinstance(request, PlanningChatRequest) for request in requests[:3])
    assert isinstance(requests[-1], PlanningPreviewRequest)
    assert 'message' not in requests[-1].model_dump()
    assert len(fixture.resume_state.payload.history) == 4
    assert all(request.resume_state.payload.generation.preview is None for request in requests)
    requests[0].resume_state.payload.history[1].tool_calls[0].args['reason'] = '다른 내용'
    assert fixture.model_dump_json() == before
    assert requests[1].resume_state == fixture.resume_state


def test_repeated_requests_have_unique_ids_but_equal_normalized_inputs():
    fixture = load_fixture()
    for case in fixture.cases:
        first, second = [make_request(fixture, case, f's1-{index}-{case.id}') for index in (1, 2)]
        hashes = [request_hashes(request) for request in (first, second)]
        assert hashes[0]['request_sha256'] != hashes[1]['request_sha256']
        assert hashes[0]['normalized_input_sha256'] == hashes[1]['normalized_input_sha256']
        assert first.resume_state == second.resume_state


def test_schedule_separates_warmup_and_reverses_each_round():
    plan = schedule(load_fixture(), 10)
    assert len(plan) == 44
    assert [case.id for phase, _, case in plan if phase == 'warmup'] == ['C1', 'C2', 'G1', 'G2']
    assert [case.id for phase, number, case in plan if number == 1] == ['C1', 'C2', 'G1', 'G2']
    assert [case.id for phase, number, case in plan if number == 2] == ['G2', 'G1', 'C2', 'C1']
    assert len(schedule(load_fixture(), 1, warmup=False)) == 4


@pytest.mark.parametrize('rounds', [0, -1, True, 1.5])
def test_invalid_rounds_are_rejected(rounds):
    with pytest.raises(ValueError):
        schedule(load_fixture(), rounds)


@pytest.mark.parametrize('change', ['preview', 'pending_change', 'different_basis', 'duplicate_case', 'unpaired_tool'])
def test_fixture_cannot_start_from_an_invalid_or_already_generated_state(change):
    data = load_fixture().model_dump(mode='json')
    generation = data['resume_state']['payload']['generation']
    if change == 'preview':
        # 공개 타입에서 생성 초안 구조가 아닌 값도 거절한다.
        generation['preview'] = {'id': 'old-preview'}
    elif change == 'pending_change':
        generation['condition_change_pending'] = True
    elif change == 'different_basis':
        generation['offer']['basis_draft']['conditions']['headcount'] = 40
    elif change == 'duplicate_case':
        data['cases'][-1] = data['cases'][0]
    else:
        del data['resume_state']['payload']['history'][2]
    with pytest.raises(ValidationError):
        LatencyFixture.model_validate(data)


def test_fixed_snapshot_can_accept_offer_and_generate_through_both_public_functions(monkeypatch):
    fixture = load_fixture()
    model = Model()
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(run_plan_generation, invoke=model))
    offer_id = fixture.resume_state.payload.generation.offer.id
    scripted(monkeypatch, [tool(GENERATE_TOOL_NAME, dict(quote='응, 만들어줘.', offer_id=offer_id)),
                           AIMessage(content='초안을 만들었어요.')])
    first = run(chat_planning(make_request(fixture, fixture.cases[2], 'chat-1')))
    second = run(generate_planning_preview(make_request(fixture, fixture.cases[3], 'button-1')))
    assert first.view.generation_result.status == second.view.generation_result.status == 'generated'
    assert first.view.generation_result.preview.trigger.source == 'chat'
    assert second.view.generation_result.preview.trigger.source == 'button'
    assert first.view.generation_result.preview.id != second.view.generation_result.preview.id
    assert len(model.calls) == 2
    assert second.next_state.payload.history == fixture.resume_state.payload.history
    assert json.loads(fixture.model_dump_json())['actual_provider_calls'] == 0


def test_valid_previous_preview_is_rejected_as_a_benchmark_start(monkeypatch):
    fixture = load_fixture()
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(run_plan_generation, invoke=Model()))
    generated = run(generate_planning_preview(make_request(fixture, fixture.cases[3], 'previous-generation')))
    data = fixture.model_dump(mode='json')
    data['resume_state']['payload']['generation']['preview'] = generated.view.generation_result.preview.model_dump(mode='json')
    with pytest.raises(ValidationError, match='생성 전 상태'):
        LatencyFixture.model_validate(data)
