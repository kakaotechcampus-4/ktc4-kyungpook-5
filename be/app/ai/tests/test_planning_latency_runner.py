"""#196: 실제 공개 흐름의 모델만 고정해 반복/실패/취소 기록과 시간 경계를 확인한다."""

import asyncio
import json
from functools import partial

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai import AITimeoutError, chat_planning, generate_planning_preview
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph
from app.ai.features.planning.agent.nodes import TOOL_NAME, GENERATE_TOOL_NAME
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.scripts import measure_planning_latency as runner
from app.ai.scripts.planning_latency_inputs import load_fixture
from app.ai.tests.test_plan_generation_graph import Model


@pytest.fixture
def fixed_models(monkeypatch):
    model = Model()
    fixture = load_fixture()

    async def invoke(messages, **kwargs):
        latest = messages[-1]
        if isinstance(latest, HumanMessage):
            if '60명' in latest.content:
                return AIMessage(content='', tool_calls=[dict(id='set-60', name=TOOL_NAME, args=dict(changes=[
                    dict(op='SET', change=dict(field='headcount', value=60), status='specified',
                         evidence=dict(message_id=latest.id, quote=latest.content))]))])
            if latest.content == '응, 만들어줘.':
                return AIMessage(content='', tool_calls=[dict(id='generate-1', name=GENERATE_TOOL_NAME,
                    args=dict(quote=latest.content, offer_id=fixture.resume_state.payload.generation.offer.id))])
            return AIMessage(content='MT, 50명, 참가비 25,000원이며 날짜는 미정이에요.')
        return AIMessage(content='요청하신 내용을 반영했어요.')

    monkeypatch.setattr(graph, 'call_agent_model', invoke)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(run_plan_generation, invoke=model))
    return model


def events(directory):
    return [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]


def execute(directory, **changes):
    options = dict(session_id='test-01', rounds=1, warmup=False, interval=0,
                   chat=chat_planning, generate=generate_planning_preview)
    options.update(changes)
    return asyncio.run(runner.run_session(directory, **options))


def test_every_round_restores_snapshot_and_runs_real_public_workflows(tmp_path, fixed_models):
    destination = tmp_path / 'session'
    report = execute(destination, rounds=2, warmup=True)
    rows = events(destination)
    started, finished = [[item for item in rows if item['event'] == event] for event in ('started', 'finished')]
    assert len(started) == len(finished) == 12
    assert report['status'] == 'completed'
    assert report['counts']['measurement'] == dict(started=8, finished=8, success=8, failed=0, interrupted=0)
    assert report['counts']['warmup']['success'] == 4
    assert all(item['outcome'] == 'success' for item in finished)
    assert all(item['history_count'] == 4 for item in started)
    assert all(item['request_bytes'] > 0 for item in started)
    assert all(item['user_message_chars'] == 0 for item in started if item['case_id'] == 'G2')
    assert all(item['request']['draft']['conditions']['headcount'] == 50 for item in started)
    assert all(item['request']['resume_state']['payload']['generation']['preview'] is None for item in started)
    assert len({item['attempt_id'] for item in started}) == 12
    for case_id in ('C1', 'C2', 'G1', 'G2'):
        assert len({item['normalized_input_sha256'] for item in started if item['case_id'] == case_id}) == 1
    assert len(fixed_models.calls) == 6  # 매 준비 실행/반복에서 G1/G2가 각각 새로 생성한다.
    assert report['environment']['mode'] == 'injected_callers'
    assert report['environment']['coverage']['stage_timings'] == runner.OBSERVATION_SCOPE
    assert report['report_version'] == 2
    assert report['environment']['model_options'] is None
    assert (destination / 'fixture.json').read_bytes() == runner.DEFAULT_FIXTURE.read_bytes()


def test_exception_is_recorded_once_without_provider_details_and_next_case_runs(tmp_path, fixed_models):
    calls = []

    async def chat(request):
        calls.append(request.message.content)
        if request.request_id.endswith('C1'):
            raise AITimeoutError('secret-key and provider error body')
        return await chat_planning(request)

    destination = tmp_path / 'failed'
    report = execute(destination, chat=chat)
    finished = [item for item in events(destination) if item['event'] == 'finished']
    assert len(finished) == 4 and len(calls) == 3
    assert finished[0]['failure'] == dict(category='timeout', error_type='AITimeoutError')
    assert finished[-1]['outcome'] == 'success'
    assert report['counts']['measurement']['failed'] == 1
    assert 'secret-key' not in (destination / 'attempts.jsonl').read_text()


def test_normal_return_with_failed_generation_is_not_counted_as_success(tmp_path, fixed_models, monkeypatch):
    monkeypatch.setattr(public_workflow, 'run_plan_generation',
                        partial(run_plan_generation, invoke=Model(AITimeoutError('private-provider'))))
    destination = tmp_path / 'generation-failure'
    report = execute(destination)
    failed = [item for item in events(destination) if item.get('outcome') == 'failed']
    assert report['counts']['measurement']['success'] == 2
    assert len(failed) == 2
    assert all(item['returned_normally'] and item['failure']['category'] == 'timeout'
               and item['failure']['stage'] == 'generation_model' for item in failed)
    assert all(item['checks']['failed_preview_preserved'] for item in failed)
    assert 'private-provider' not in (destination / 'attempts.jsonl').read_text()


def test_reply_without_requested_change_or_generation_is_not_success(tmp_path, fixed_models, monkeypatch):
    async def reply_only(*args, **kwargs):
        return AIMessage(content='알겠어요.')

    monkeypatch.setattr(graph, 'call_agent_model', reply_only)
    destination = tmp_path / 'wrong-behavior'
    report = execute(destination)
    finished = [item for item in events(destination) if item['event'] == 'finished']
    assert report['counts']['measurement']['success'] == 2  # C1과 직접 버튼 생성만 성공한다.
    assert finished[1]['checks']['conditions_match'] is False
    assert finished[2]['checks']['generated'] is False
    assert finished[1]['returned_normally'] and finished[2]['returned_normally']


def test_timing_stops_before_result_validation_and_output(tmp_path, fixed_models, monkeypatch):
    tick = [0]
    inspected = runner.inspect_result

    async def timed_chat(request):
        result = await chat_planning(request)
        tick[0] += 5_000_000
        return result

    async def timed_button(request):
        result = await generate_planning_preview(request)
        tick[0] += 5_000_000
        return result

    def expensive_inspection(*args):
        tick[0] += 100_000_000
        return inspected(*args)

    monkeypatch.setattr(runner, 'inspect_result', expensive_inspection)
    destination = tmp_path / 'timing'
    execute(destination, chat=timed_chat, generate=timed_button, clock=lambda: tick[0])
    assert [item['ai_request_ms'] for item in events(destination) if item['event'] == 'finished'] == [5.0] * 4


def test_cancellation_closes_active_attempt_and_marks_session_incomplete(tmp_path, fixed_models):
    async def cancel(request):
        raise asyncio.CancelledError

    destination = tmp_path / 'cancelled'
    with pytest.raises(asyncio.CancelledError):
        execute(destination, chat=cancel)
    report = json.loads((destination / 'session.json').read_text())
    assert report['status'] == 'interrupted'
    assert report['counts']['measurement']['interrupted'] == 1
    assert [item['event'] for item in events(destination)] == ['started', 'finished']
    assert events(destination)[-1]['outcome'] == 'interrupted'


def test_abrupt_exit_keeps_started_event_instead_of_claiming_completion(tmp_path, fixed_models):
    class AbruptExit(BaseException):
        pass

    async def stop(request):
        raise AbruptExit

    destination = tmp_path / 'abrupt'
    with pytest.raises(AbruptExit):
        execute(destination, chat=stop)
    assert [item['event'] for item in events(destination)] == ['started']
    report = json.loads((destination / 'session.json').read_text())
    assert report['status'] == 'runner_failed'
    assert report['counts']['measurement']['started'] == 1
    assert report['counts']['measurement']['finished'] == 0


def test_output_collision_does_not_overwrite_or_invoke_callers(tmp_path):
    marker = tmp_path / 'original.txt'
    marker.write_text('preserve')

    async def unexpected(*args):
        pytest.fail('기존 폴더를 만나면 호출하면 안 됩니다')

    with pytest.raises(FileExistsError):
        execute(tmp_path, chat=unexpected, generate=unexpected)
    assert marker.read_text() == 'preserve'
    assert not (tmp_path / 'session.json').exists()


def test_request_mutation_is_detected_and_does_not_contaminate_next_request(tmp_path, fixed_models):
    async def mutate(request):
        result = await chat_planning(request)
        request.resume_state.payload.history[1].tool_calls[0].args['reason'] = 'mutated'
        return result

    destination = tmp_path / 'mutated'
    report = execute(destination, chat=mutate)
    finished = [item for item in events(destination) if item['event'] == 'finished']
    assert report['counts']['measurement']['failed'] == 3
    assert all(not item['checks']['request_unchanged'] for item in finished[:3])
    assert finished[-1]['outcome'] == 'success'


def test_invalid_result_does_not_leak_its_body(tmp_path):
    async def invalid(request):
        return 'secret-response'

    destination = tmp_path / 'invalid'
    report = execute(destination, chat=invalid, generate=invalid)
    assert report['counts']['measurement']['failed'] == 4
    assert all(item['failure']['category'] == 'invalid_result'
               for item in events(destination) if item['event'] == 'finished')
    assert 'secret-response' not in (destination / 'attempts.jsonl').read_text()


def test_dry_run_validates_all_requests_without_loading_api_settings(monkeypatch, capsys):
    def unexpected():
        pytest.fail('dry-run은 API 설정을 읽지 않습니다')

    monkeypatch.setattr(runner, 'AISettings', unexpected)
    monkeypatch.setattr('sys.argv', ['measure', '--session-id', 'dry-01', '--rounds', '1', '--dry-run', '--no-warmup'])
    assert runner.main() == 0
    data = json.loads(capsys.readouterr().out)
    assert data['mode'] == 'dry_run'
    assert [item['case_id'] for item in data['attempts']] == ['C1', 'C2', 'G1', 'G2']


@pytest.mark.parametrize('interval', [-1, float('nan'), float('inf')])
def test_invalid_interval_fails_before_creating_results(tmp_path, interval):
    destination = tmp_path / 'invalid-interval'
    with pytest.raises(ValueError):
        execute(destination, interval=interval)
    assert not destination.exists()


def test_no_gap_after_last_request_and_sleep_is_outside_timer(tmp_path, fixed_models):
    gaps = []

    async def sleep(seconds):
        gaps.append(seconds)

    execute(tmp_path / 'gaps', interval=1, sleep=sleep)
    assert gaps == [1, 1, 1]
