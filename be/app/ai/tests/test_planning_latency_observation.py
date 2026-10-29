"""고정 응답과 명시적으로 전진하는 시계로 실제 Graph의 구간과 실패 시도를 확인한다."""

import asyncio
import json
from functools import partial
from threading import Event

import pytest
from langchain_core.messages import AIMessage

from app.ai import AITimeoutError, AIOutputLimitError, chat_planning, generate_planning_preview
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph
from app.ai.features.planning.agent.nodes import GENERATE_TOOL_NAME
from app.ai.features.planning.generation import graph as generation_graph, model as generation_model
from app.ai.scripts.measure_planning_latency import measure_attempt
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request
from app.ai.scripts.planning_latency_observation import CURRENT_TRACE, capture_request, install_observers, validate_observation
from app.ai.tests.test_plan_generation_graph import composition


class Clock:
    def __init__(self):
        self.value = 0

    def __call__(self):
        return self.value

    def advance(self, milliseconds):
        self.value += int(milliseconds * 1_000_000)


def configure(monkeypatch, clock, *, generations=None, retry=False, agent_error=None, use_default=False):
    fixture = load_fixture()
    calls = []
    outputs = iter(generations if generations is not None else [composition()])
    offer_id = fixture.resume_state.payload.generation.offer.id

    def generate_tool(number):
        return AIMessage(content='', tool_calls=[dict(id=f'generate-{number}', name=GENERATE_TOOL_NAME,
                         args=dict(quote='응, 만들어줘.', offer_id=offer_id))])

    responses = iter([generate_tool(1), *([generate_tool(2)] if retry else []), AIMessage(content='초안을 확인해 주세요.')])

    async def agent(*args, **kwargs):
        if agent_error:
            clock.advance(10)
            raise agent_error
        response = next(responses)
        clock.advance(10 if response.tool_calls else 5)
        return response

    async def generate(messages, schema, **kwargs):
        clock.advance(30)
        calls.append(schema)
        value = next(outputs)
        if isinstance(value, BaseException):
            raise value
        return value

    original_validate = generation_graph.validate_plan

    def validate(state):
        clock.advance(2)
        return original_validate(state)

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    monkeypatch.setattr(generation_graph, 'validate_plan', validate)
    if use_default:
        monkeypatch.setattr(generation_model, 'build_plan_model', lambda: object())
        monkeypatch.setattr(generation_model, 'ainvoke_structured', generate)
    else:
        monkeypatch.setattr(public_workflow, 'run_plan_generation',
                            partial(generation_graph.run_plan_generation, invoke=generate))
    return fixture, calls


def measured(fixture, clock, case_id='G1'):
    case = next(item for item in fixture.cases if item.id == case_id)
    request = make_request(fixture, case, f'observed-{case_id}')
    call = generate_planning_preview if case_id == 'G2' else chat_planning
    with install_observers():
        result, interrupted = asyncio.run(measure_attempt(case, request, call, clock=clock))
    assert not interrupted
    return result


def test_chat_generation_has_correct_nested_intervals(monkeypatch):
    clock = Clock()
    fixture, calls = configure(monkeypatch, clock)
    result = measured(fixture, clock)
    spans = result['observation']['spans']
    assert result['outcome'] == 'success' and result['ai_request_ms'] == 47
    assert [(item['stage'], item['parent_id'], item['start_ms'], item['end_ms']) for item in spans] == [
        ('agent_model', None, 0, 10), ('generation', None, 10, 42),
        ('compose_plan', 2, 10, 40), ('generation_model', 3, 10, 40),
        ('validate_plan', 2, 40, 42), ('agent_model', None, 42, 47),
    ]
    assert result['observation']['model_call_attempts'] == dict(agent_model=2, generation_model=1)
    assert all(item['input_message_count'] > 0 and item['message_text_chars'] > 0
               for item in spans if item['stage'] in ('agent_model', 'generation_model'))
    assert len(calls) == 1 and CURRENT_TRACE.get() is None


def test_button_uses_same_generation_without_agent_model(monkeypatch):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock)
    result = measured(fixture, clock, 'G2')
    assert result['outcome'] == 'success' and result['ai_request_ms'] == 32
    assert result['observation']['model_call_attempts'] == dict(agent_model=0, generation_model=1)
    assert [item['stage'] for item in result['observation']['spans']] == [
        'generation', 'compose_plan', 'generation_model', 'validate_plan']


@pytest.mark.parametrize('error, category', [(AITimeoutError('private-provider'), 'timeout'),
                                           (AIOutputLimitError('private-provider'), 'output_limit')])
def test_handled_generation_error_keeps_failed_model_attempt(monkeypatch, error, category):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock, generations=[error])
    result = measured(fixture, clock)
    assert result['outcome'] == 'failed' and result['returned_normally']
    assert result['failure'] == dict(category=category, error_type=type(error).__name__, stage='generation_model', span_id=4)
    assert result['observation']['model_call_attempts'] == dict(agent_model=2, generation_model=1)
    assert not any(item['stage'] == 'validate_plan' for item in result['observation']['spans'])
    assert 'private-provider' not in json.dumps(result['observation'])


def test_plan_validation_error_is_distinct_from_model_output(monkeypatch):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock, generations=[composition(excluded_steps=[])])
    result = measured(fixture, clock)
    assert result['failure']['category'] == 'invalid_plan' and result['failure']['stage'] == 'validate_plan'
    assert next(item for item in result['observation']['spans'] if item['stage'] == 'generation_model')['outcome'] == 'ok'


def test_agent_model_failure_counts_attempt_before_success_counter(monkeypatch):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock, agent_error=AITimeoutError('private-provider'))
    result = measured(fixture, clock)
    assert result['outcome'] == 'failed' and not result['returned_normally']
    assert result['failure']['stage'] == 'agent_model' and result['failure']['category'] == 'timeout'
    assert result['observation']['model_call_attempts'] == dict(agent_model=1, generation_model=0)


def test_agent_retry_preserves_failed_generation_even_if_request_succeeds(monkeypatch):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock, generations=[AITimeoutError('hidden'), composition()], retry=True)
    result = measured(fixture, clock)
    assert result['outcome'] == 'success' and result['ai_request_ms'] == 87
    assert result['failure'] is None
    assert result['observation']['model_call_attempts'] == dict(agent_model=3, generation_model=2)
    roots = [item for item in result['observation']['spans'] if item['stage'] == 'generation']
    assert [(item['outcome'], item['duration_ms']) for item in roots] == [('error', 30), ('ok', 32)]
    from app.ai.scripts.planning_latency_summary import summarize_observations
    summary = summarize_observations([result])['by_stage']['generation']
    assert summary['calls'] == 2 and summary['error_calls'] == 1
    assert summary['per_completed_request_total_ms']['p50_ms'] == 62


def test_definition_time_default_invoke_is_also_observed(monkeypatch):
    clock = Clock()
    fixture, calls = configure(monkeypatch, clock, use_default=True)
    result = measured(fixture, clock, 'G2')
    assert result['outcome'] == 'success' and len(calls) == 1
    assert result['observation']['model_call_attempts']['generation_model'] == 1


def test_observers_are_restored_and_overlapping_install_is_rejected():
    originals = (agent_graph.call_agent_model, public_workflow.run_plan_generation,
                 generation_graph.compose_plan, generation_graph.validate_plan)
    with pytest.raises(ValueError):
        with install_observers():
            with pytest.raises(RuntimeError):
                with install_observers():
                    pass
            raise ValueError('test interruption')
    assert originals == (agent_graph.call_agent_model, public_workflow.run_plan_generation,
                         generation_graph.compose_plan, generation_graph.validate_plan)
    with install_observers():
        pass


def test_calls_outside_request_capture_pass_through(monkeypatch):
    expected = AIMessage(content='unchanged')
    seen = []

    async def original(*args, **kwargs):
        seen.append((args, kwargs))
        return expected

    monkeypatch.setattr(agent_graph, 'call_agent_model', original)
    with install_observers():
        assert asyncio.run(agent_graph.call_agent_model([], allow_tools=False)) is expected
        assert CURRENT_TRACE.get() is None
    assert seen == [(([],), {'allow_tools': False})]


def test_separate_async_contexts_do_not_share_spans():
    async def one(clock):
        with capture_request(clock) as trace:
            trace.origin_ns = clock()
            with trace.span('agent_model'):
                await asyncio.sleep(0)
                clock.advance(3)
            return trace.snapshot()

    async def scenario():
        return await asyncio.gather(one(Clock()), one(Clock()))

    first, second = asyncio.run(scenario())
    assert len(first['spans']) == len(second['spans']) == 1
    assert first['spans'][0]['id'] == second['spans'][0]['id'] == 1
    assert first['spans'][0]['duration_ms'] == second['spans'][0]['duration_ms'] == 3


def test_sync_validation_running_after_cancellation_is_not_zero_ms(monkeypatch):
    clock = Clock()
    fixture, _ = configure(monkeypatch, clock)
    entered, release, exited = Event(), Event(), Event()
    original_validate = generation_graph.validate_plan

    def blocked(state):
        entered.set()
        try:
            if not release.wait(3):
                raise TimeoutError('test synchronization')
            return original_validate(state)
        finally:
            exited.set()

    monkeypatch.setattr(generation_graph, 'validate_plan', blocked)
    case = fixture.cases[2]
    request = make_request(fixture, case, 'cancel-validation')

    async def scenario():
        with install_observers():
            task = asyncio.create_task(measure_attempt(case, request, chat_planning, clock=clock))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                return await task
            finally:
                release.set()

    result, interrupted = asyncio.run(scenario())
    assert exited.wait(2) and interrupted
    observed = result['observation']
    validate = next(item for item in observed['spans'] if item['stage'] == 'validate_plan')
    assert not observed['complete'] and validate['outcome'] == 'running'
    assert validate['end_ms'] is None and validate['duration_ms'] is None
    validate_observation(observed, result['ai_request_ms'], allow_pending=True)
    from app.ai.scripts.planning_latency_summary import summarize_observations
    summary = summarize_observations([result])['by_stage']['validate_plan']
    assert summary['pending_calls'] == 1 and summary['per_call_ms']['n'] == 0


def test_snapshot_freezes_request_end_even_if_worker_finishes_later():
    clock = Clock()
    with capture_request(clock) as trace:
        trace.origin_ns = clock()
        with trace.span('agent_model', input_message_count=1, message_text_chars=1):
            clock.advance(10)
    observed = trace.snapshot(request_ms=5)
    assert not observed['complete']
    assert observed['spans'][0]['end_ms'] is None
    validate_observation(observed, 5, allow_pending=True)
