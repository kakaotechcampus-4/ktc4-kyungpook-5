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
    assert summary['coverage']['token_usage'] == 'langchain_usage_metadata_last_response'
    # 고정 응답은 LangChain 모델 실행을 거치지 않아 토큰이 없다. 0이 아니라 이유별 건수로 남는다.
    usage = stages['agent_model']['usage']
    assert usage['observed_calls'] == 0 and usage['missing_calls'] == dict(not_reported=2)
    assert usage['per_call']['output_tokens']['p50'] is None
    assert usage['reasoning_share_of_output'] == dict(calls=0, ratio=None)


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
    assert old['coverage']['token_usage'] is None
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


# --- #263 토큰 집계 -----------------------------------------------------------

def finished_with(*usages, stage='agent_model', version=2):
    """모델 구간 하나짜리 완료 요청. usage 자리에 (토큰 dict 또는 None, 없을 때 이유)를 받는다."""
    items = []
    for number, (usage, missing) in enumerate(usages, 1):
        span = dict(id=1, parent_id=None, stage=stage, start_ms=0, end_ms=10, duration_ms=10,
                    outcome='ok' if missing != 'no_response' else 'error',
                    failure_code=None if missing != 'no_response' else 'timeout', error_type=None,
                    input_message_count=1, message_text_chars=1)
        if version == 2:
            span.update(usage=usage, usage_missing=missing)
        items.append(dict(outcome='success', ai_request_ms=10, observation=dict(
            version=version, scope='planning_function_wrappers_v1', spans=[span], complete=True,
            model_call_attempts=dict(agent_model=int(stage == 'agent_model'), generation_model=int(stage == 'generation_model')))))
    return items


def tokens(input_tokens, output_tokens, reasoning_tokens, cached_input_tokens):
    return dict(input_tokens=input_tokens, output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens, cached_input_tokens=cached_input_tokens)


def test_usage_shares_are_ratio_of_totals_not_mean_of_ratios():
    from app.ai.scripts.planning_latency_summary import summarize_observations
    finished = finished_with((tokens(1000, 100, 90, 0), None), (tokens(1200, 1000, 100, 600), None),
                             (None, 'not_reported'), (None, 'no_response'))
    usage = summarize_observations(finished)['by_stage']['agent_model']['usage']
    assert usage['observed_calls'] == 2
    assert usage['missing_calls'] == dict(no_response=1, not_reported=1)
    assert usage['per_call']['output_tokens'] == dict(n=2, p50=550, p95=955, mean=550, max=1000)
    assert usage['totals'] == tokens(2200, 1100, 190, 600)
    # 호출별 비율의 평균(0.5)이 아니라 190 / 1,100이다.
    assert usage['reasoning_share_of_output'] == dict(calls=2, ratio=190 / 1100)
    assert usage['cached_share_of_input'] == dict(calls=2, ratio=600 / 2200)


def test_missing_detail_tokens_are_left_out_of_that_share_only():
    from app.ai.scripts.planning_latency_summary import summarize_observations
    finished = finished_with((tokens(3000, 5000, 3000, None), None), (tokens(2000, 1000, None, 500), None),
                             stage='generation_model')
    usage = summarize_observations(finished)['by_stage']['generation_model']['usage']
    assert usage['per_call']['reasoning_tokens']['n'] == 1 and usage['per_call']['output_tokens']['n'] == 2
    assert usage['reasoning_share_of_output'] == dict(calls=1, ratio=0.6)
    assert usage['cached_share_of_input'] == dict(calls=1, ratio=0.25)


def test_legacy_observation_reports_usage_as_unobserved():
    from app.ai.scripts.planning_latency_summary import summarize_observations
    stage = summarize_observations(finished_with((None, None), version=1))['by_stage']['agent_model']
    assert stage['calls'] == 1 and stage['usage'] is None


def test_console_table_shows_token_summary_only_when_observed():
    from app.ai.scripts.planning_latency_summary import summarize_group
    observed = summarize_group([{}], [{}], finished_with((tokens(4400, 100, 20, 0), None)))
    legacy = summarize_group([{}], [{}], finished_with((None, None), version=1))
    summary = dict(mode='real_model', session_count=1, complete=True, observation_complete=True,
                   groups=dict(measurement=dict(C1=observed, C2=legacy)))
    table = aggregate.render_table(summary)
    assert '입력 중 캐시' in table
    assert 'C1 | agent_model | 1 | 1 | 4400 | 100 | 20.0% | 0.0%' in table
    assert 'C2 | agent_model' not in table
