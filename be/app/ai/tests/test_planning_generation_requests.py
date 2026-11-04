"""#239 진단이 경로·실패·입력 보존을 올바르게 기록하는지 실제 Graph로 확인한다."""

import asyncio
from copy import deepcopy
from functools import partial
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
import pytest

from app.ai import AIConfigError, AITimeoutError, parse_resume_state
from app.ai.config import AISettings
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph, nodes
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.scripts import check_planning_generation_requests as check
from app.ai.scripts.planning_latency_observation import install_observers, validate_observation
from app.ai.tests.test_plan_generation_graph import composition


def last_turn(messages):
    """실행 문맥(시스템 메시지)이 맨 끝에 붙어도(planning-agent-v8, #269) 마지막 대화 메시지를 본다."""
    return next(m for m in reversed(messages) if not isinstance(m, SystemMessage))


@pytest.fixture(scope='module')
def fixture():
    return asyncio.run(check.build_fixture())


def configure(monkeypatch, fixture, *, stale_id=False, error=None):
    calls = []
    offer_id = fixture['cases'][0]['resume_state']['payload']['generation']['offer']['id']

    async def agent(messages, **kwargs):
        if isinstance(last_turn(messages), ToolMessage):
            return AIMessage(content='처리 결과를 확인해 주세요.')
        human = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
        args = dict(quote=human.text)
        if stale_id:
            args['offer_id'] = offer_id
        return AIMessage(content='', tool_calls=[check.tool(nodes.GENERATE_TOOL_NAME, args, f'gen-{human.id}')])

    async def generate(messages, schema):
        calls.append(messages)
        if error:
            raise error
        return composition()

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(run_plan_generation, invoke=generate))
    return calls


def measured(fixture, case_id='changed_headcount', route='chat'):
    request = check.make_request(fixture, case_id, route, f'test-{case_id}-{route}')
    original = request.model_dump_json()
    with install_observers():
        row, interrupted = asyncio.run(check.attempt(request))
    assert not interrupted
    assert request.model_dump_json() == original
    validate_observation(row['observation'], row['ai_request_ms'])
    return row


def test_fixture_is_real_serializable_history_with_only_the_intended_change(fixture):
    states = [parse_resume_state(json.dumps(c['resume_state'])) for c in fixture['cases']]
    assert [s.payload.basis_draft.conditions.headcount for s in states] == [30, 40, 30]
    assert [s.payload.basis_draft.condition_meta['start_date'].status for s in states] == [
        'tentative', 'tentative', 'specified']
    assert all(s.payload.generation.offer == states[0].payload.generation.offer for s in states)
    assert all(s.payload.generation.preview is None for s in states)
    assert states[1].payload.history[:len(states[0].payload.history)] == states[0].payload.history
    assert any(m.name == nodes.TOOL_NAME for m in states[2].payload.history)


def test_chat_and_button_restore_the_same_independent_snapshot(fixture):
    before = deepcopy(fixture)
    chat = check.make_request(fixture, 'specified_dates', 'chat', 'one')
    button = check.make_request(fixture, 'specified_dates', 'button', 'two')
    assert chat.draft == button.draft and chat.resume_state == button.resume_state
    chat.draft.condition_meta.clear()
    assert button.draft.condition_meta and fixture == before
    assert 'message' not in button.model_dump()


@pytest.mark.parametrize('case_id', check.CASE_IDS)
@pytest.mark.parametrize('route', check.ROUTES)
def test_both_paths_reach_the_same_real_generation_graph(monkeypatch, fixture, case_id, route):
    calls = configure(monkeypatch, fixture)
    row = measured(fixture, case_id, route)
    assert row['outcome'] == 'success' and row['generation_entered'] and len(calls) == 1
    assert all(row['checks'].values())
    assert row['observation']['model_call_attempts'] == dict(agent_model=2 if route == 'chat' else 0, generation_model=1)


@pytest.mark.parametrize('case_id', check.CASE_IDS[1:])
def test_old_id_blocks_before_generation_and_direct_request_succeeds(monkeypatch, fixture, case_id):
    calls = configure(monkeypatch, fixture, stale_id=True)
    row = measured(fixture, case_id)
    assert row['outcome'] == 'failed' and not calls and not row['generation_entered']
    assert row['stale_offer_id_used'] and row['generation_status'] == 'needs_clarification'
    assert row['tool_activity']['results'][0]['status'] == 'needs_clarification'
    assert row['checks']['conditions_preserved'] and row['checks']['previous_preview_preserved']
    calls = configure(monkeypatch, fixture)
    direct = measured(fixture, case_id)
    assert direct['outcome'] == 'success' and len(calls) == 1 and not direct['stale_offer_id_used']


def test_current_offer_id_is_valid_and_not_reported_as_stale(monkeypatch, fixture):
    configure(monkeypatch, fixture, stale_id=True)
    row = measured(fixture, 'current_offer')
    assert row['outcome'] == 'success' and not row['stale_offer_id_used']


def test_model_timeout_after_generation_is_not_misreported_as_intent_failure(monkeypatch, fixture):
    configure(monkeypatch, fixture, error=AITimeoutError('provider-private'))
    row = measured(fixture)
    assert row['generation_entered'] and row['generation_status'] == 'failed'
    assert row['failure_category'] == 'timeout'
    assert row['checks']['draft_preserved'] and row['checks']['previous_preview_preserved']
    assert 'provider-private' not in json.dumps(row)


def test_tools_are_preserved_if_final_reply_raises(monkeypatch, fixture):
    configure(monkeypatch, fixture, stale_id=True)
    original = agent_graph.call_agent_model

    async def agent(messages, **kwargs):
        if isinstance(last_turn(messages), ToolMessage):
            raise AIConfigError('private-settings')
        return await original(messages, **kwargs)

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    row = measured(fixture)
    assert not row['returned_normally'] and row['stop_session'] == 'configuration_error'
    assert row['stale_offer_id_used'] and row['tool_activity']['results'][0]['status'] == 'needs_clarification'
    assert row['failure_stage'] == 'agent_model'
    assert 'private-settings' not in json.dumps(row)


def test_observation_does_not_save_reasoning_blocks(monkeypatch, fixture):
    configure(monkeypatch, fixture)
    original = agent_graph.call_agent_model

    async def agent(*args, **kwargs):
        response = await original(*args, **kwargs)
        if response.tool_calls:
            response.content = [dict(type='reasoning', text='private-inner-thought')]
        return response

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    row = measured(fixture)
    assert row['outcome'] == 'success'
    assert 'private-inner-thought' not in json.dumps(row)


def test_validation_rejects_fixture_that_loses_the_old_offer(fixture):
    broken = deepcopy(fixture)
    payload = broken['cases'][1]['resume_state']['payload']
    payload['generation']['offer']['basis_draft'] = payload['basis_draft']
    with pytest.raises(ValueError):
        check.validate_fixture(broken)


def test_schedule_alternates_paths_and_summary_keeps_failures():
    plan = check.schedule(3)
    assert len(plan) == 18
    assert plan[0] == (1, 'current_offer', 'chat')
    assert plan[6] == (2, 'specified_dates', 'button')
    rows = [dict(case_id='changed_headcount', route='chat', outcome='failed', generation_entered=False,
                 stale_offer_id_used=True, failure_category='before_generation', checks=dict(generated=False)),
            dict(case_id='changed_headcount', route='chat', outcome='success', generation_entered=True,
                 stale_offer_id_used=False, checks=dict(generated=True))]
    group = check.summarize(rows)['changed_headcount']['chat']
    assert group['finished'] == 2 and group['success'] == 1 and group['entered'] == 1
    assert group['stale_offer_id_used'] == 1 and group['failures'] == dict(before_generation=1)
    assert check.summarize([])['changed_headcount']['chat']['finished'] == 0


@pytest.mark.parametrize('stop', [False, True])
def test_session_keeps_all_attempts_or_marks_configuration_stop(monkeypatch, fixture, tmp_path, stop):
    calls = configure(monkeypatch, fixture)
    settings = AISettings(api_base_url='https://invalid.test/v1', api_key='never-record-this', model='injected-model')
    monkeypatch.setattr(check, 'AISettings', lambda: settings)

    async def no_wait(*args):
        pass

    monkeypatch.setattr(check.asyncio, 'sleep', no_wait)
    if stop:
        async def broken(*args, **kwargs):
            raise AIConfigError('provider-private-settings')
        monkeypatch.setattr(agent_graph, 'call_agent_model', broken)
    source = tmp_path / 'fixture.json'
    source.write_text(json.dumps(fixture))
    destination = tmp_path / 'run'
    report = asyncio.run(check.run(destination, source, rounds=1))
    events = [json.loads(line) for line in (destination / 'attempts.jsonl').read_text().splitlines()]
    assert len(events) == (2 if stop else 12)
    assert report['status'] == ('stopped_configuration_error' if stop else 'completed')
    assert report['planned'] == 6 and report['finished'] == (1 if stop else 6)
    assert len(calls) == (0 if stop else 6)
    assert (destination / 'fixture.json').read_bytes() == source.read_bytes()
    assert 'never-record-this' not in (destination / 'session.json').read_text()
    assert 'provider-private-settings' not in (destination / 'attempts.jsonl').read_text()
    original = (destination / 'session.json').read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(check.run(destination, source, rounds=1))
    assert (destination / 'session.json').read_bytes() == original


def test_session_cancellation_preserves_started_and_finished_events(monkeypatch, fixture, tmp_path):
    configure(monkeypatch, fixture)
    settings = AISettings(api_base_url='https://invalid.test/v1', api_key='fake', model='injected-model')
    monkeypatch.setattr(check, 'AISettings', lambda: settings)

    source = tmp_path / 'fixture.json'
    source.write_text(json.dumps(fixture))
    destination = tmp_path / 'interrupted'

    async def cancel_running_session():
        entered = asyncio.Event()

        async def waiting(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        # Node 내부의 CancelledError 주입과 달리, 사용자가 실행 중인 세션을 취소한다.
        monkeypatch.setattr(agent_graph, 'call_agent_model', waiting)
        task = asyncio.create_task(check.run(destination, source, rounds=1))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_running_session())
    report = json.loads((destination / 'session.json').read_text())
    events = [json.loads(line) for line in (destination / 'attempts.jsonl').read_text().splitlines()]
    assert report['status'] == 'interrupted' and report['finished'] == 1 and report['planned'] == 6
    assert [e['event'] for e in events] == ['started', 'finished']
    assert events[-1]['outcome'] == 'interrupted' and not events[-1]['returned_normally']
