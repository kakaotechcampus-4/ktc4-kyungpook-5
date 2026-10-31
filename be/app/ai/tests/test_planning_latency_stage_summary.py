"""실제 반복 기록 → 구간 검증 → 집계까지 고정 응답과 가상 시계로 연결한다."""

import asyncio
import json
import shutil
from functools import partial

import pytest

from app.ai import chat_planning, generate_planning_preview
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph
from app.ai.features.planning.generation import graph as generation_graph
from app.ai.scripts import measure_planning_latency as runner, summarize_planning_latency as aggregate
from app.ai.tests.test_planning_latency_observation import Clock
from app.ai.tests.test_planning_latency_runner import fixed_models  # noqa: F401


def timed_models(monkeypatch, model, *, generation_error=None, generation_wait=None):
    clock = Clock()
    original_agent = agent_graph.call_agent_model
    original_validate = generation_graph.validate_plan

    async def agent(*args, **kwargs):
        result = await original_agent(*args, **kwargs)
        clock.advance(10 if result.tool_calls else 5)
        return result

    async def generate(*args, **kwargs):
        clock.advance(30)
        if generation_wait is not None:
            generation_wait.set()
            await asyncio.Event().wait()
        if generation_error is not None:
            raise generation_error
        return await model(*args, **kwargs)

    def validate(state):
        clock.advance(2)
        return original_validate(state)

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    monkeypatch.setattr(generation_graph, 'validate_plan', validate)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(generation_graph.run_plan_generation, invoke=generate))
    return clock


def write_session(directory, clock):
    return asyncio.run(runner.run_session(directory, session_id='observed-01', rounds=1, warmup=False,
                      interval=0, chat=chat_planning, generate=generate_planning_preview, clock=clock))


def rows(directory):
    return [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]


def replace_rows(directory, data):
    (directory / 'attempts.jsonl').write_text(''.join(json.dumps(item) + '\n' for item in data))


def test_stage_calls_and_request_totals_are_not_double_counted(tmp_path, monkeypatch, fixed_models):
    clock = timed_models(monkeypatch, fixed_models)
    directory = tmp_path / 'stages'
    write_session(directory, clock)
    summary = aggregate.aggregate_sessions([directory])
    group = summary['groups']['measurement']['G1']
    observed = group['observation']
    assert group['success_ms']['p50_ms'] == 47
    assert observed['model_call_attempts'] == dict(agent_model=2, generation_model=1)
    stages = observed['by_stage']
    assert stages['agent_model']['calls'] == 2
    assert stages['agent_model']['per_call_ms']['p50_ms'] == 7.5
    assert stages['agent_model']['per_completed_request_total_ms']['p50_ms'] == 15
    assert stages['generation']['per_call_ms']['p50_ms'] == 32
    assert stages['compose_plan']['per_call_ms']['p50_ms'] == stages['generation_model']['per_call_ms']['p50_ms'] == 30
    assert stages['validate_plan']['per_call_ms']['p50_ms'] == 2
    button = summary['groups']['measurement']['G2']['observation']['by_stage']['agent_model']
    assert button['calls'] == 0 and button['per_call_ms']['p95_ms'] is None
    assert button['per_completed_request_total_ms']['p95_ms'] == 0
    assert summary['coverage']['stage_timings'] == runner.OBSERVATION_SCOPE
    assert summary['coverage']['http_attempts'] is None


@pytest.mark.parametrize('mutation', ['duration', 'parent', 'count', 'bounds', 'overlap', 'origin', 'missing', 'scope', 'complete_flag', 'pending_success'])
def test_invalid_spans_cannot_be_aggregated(tmp_path, monkeypatch, fixed_models, mutation):
    clock = timed_models(monkeypatch, fixed_models)
    directory = tmp_path / 'invalid'
    write_session(directory, clock)
    data = rows(directory)
    target = next(item for item in data if item['event'] == 'finished' and item['case_id'] == 'G1')
    trace = target['observation']
    if mutation == 'duration':
        trace['spans'][3]['duration_ms'] = 999
    elif mutation == 'parent':
        trace['spans'][3]['parent_id'] = 999
    elif mutation == 'count':
        trace['model_call_attempts']['agent_model'] += 1
    elif mutation == 'bounds':
        trace['spans'][3].update(end_ms=1000, duration_ms=990)
    elif mutation == 'overlap':
        trace['spans'][-1].update(start_ms=10, end_ms=15, duration_ms=5)
    elif mutation == 'origin':
        trace['spans'][1]['failure_origin_id'] = 6
    elif mutation == 'missing':
        del target['observation']
    elif mutation == 'scope':
        trace['scope'] = 'unsupported'
    elif mutation == 'complete_flag':
        trace['complete'] = False
    else:
        trace['spans'][-1].update(outcome='running', end_ms=None, duration_ms=None)
        trace['complete'] = False
    replace_rows(directory, data)
    with pytest.raises(aggregate.RecordError, match='구간 관측'):
        aggregate.aggregate_sessions([directory])


def test_old_records_keep_unknown_stages_and_do_not_mix_with_new_records(tmp_path, monkeypatch, fixed_models):
    clock = timed_models(monkeypatch, fixed_models)
    current = tmp_path / 'current'
    write_session(current, clock)
    legacy = tmp_path / 'legacy'
    shutil.copytree(current, legacy)
    path = legacy / 'session.json'
    metadata = json.loads(path.read_text())
    metadata.update(report_version=1, session_id='legacy-01')
    metadata['environment']['coverage'] = dict(timing='public_function_only', stage_timings=None)
    path.write_text(json.dumps(metadata))
    data = rows(legacy)
    for item in data:
        item.pop('observation', None)
    replace_rows(legacy, data)
    old = aggregate.aggregate_sessions([legacy])
    assert old['groups']['measurement']['G1']['observation'] is None
    assert old['coverage']['model_call_attempts'] is None
    with pytest.raises(aggregate.RecordError, match='다른 세션'):
        aggregate.aggregate_sessions([legacy, current])


def test_cancelled_model_wait_remains_separate_from_completion_times(tmp_path, monkeypatch, fixed_models):
    entered = asyncio.Event()
    clock = timed_models(monkeypatch, fixed_models, generation_wait=entered)
    directory = tmp_path / 'cancelled'

    async def scenario():
        task = asyncio.create_task(runner.run_session(directory, session_id='cancelled-01', rounds=1,
            warmup=False, interval=0, chat=chat_planning, generate=generate_planning_preview, clock=clock))
        await entered.wait()
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scenario())
    summary = aggregate.aggregate_sessions([directory])
    group = summary['groups']['measurement']['G1']
    assert not summary['complete'] and group['counts']['interrupted'] == 1
    assert group['interrupted_wait_ms']['p50_ms'] == 40
    observed = group['observation']
    assert observed['model_call_attempts'] == dict(agent_model=1, generation_model=1)
    generation = observed['by_stage']['generation_model']
    assert generation['calls'] == generation['interrupted_calls'] == 1
    assert generation['per_call_ms']['n'] == generation['per_completed_request_total_ms']['n'] == 0
    assert generation['interrupted_wait_ms']['p50_ms'] == 30
