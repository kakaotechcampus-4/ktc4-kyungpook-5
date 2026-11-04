"""제한된 수집의 중단 시점·실패 보존·미확보/오류/취소 기록을 실제 공개 Graph로 확인한다."""

import asyncio
import json

import pytest

from app.ai import AIConfigError
from app.ai.config import AISettings
from app.ai.features.planning.agent import graph as agent_graph
from app.ai.scripts import capture_planning_validation as runner
from app.ai.scripts import planning_validation_diagnostics as diag
from app.ai.tests.test_plan_generation_graph import composition
from app.ai.tests.test_planning_validation_diagnostics import chat_request, retry_models


@pytest.fixture
def settings(monkeypatch):
    value = AISettings(api_base_url='https://invalid.test/v1', api_key='private-sampler-key', model='injected-model')
    monkeypatch.setattr(runner, 'AISettings', lambda: value)

    async def no_wait(*args):
        pass

    monkeypatch.setattr(runner.asyncio, 'sleep', no_wait)
    return value


def events(destination):
    return [json.loads(line) for line in (destination / 'attempts.jsonl').read_text().splitlines()]


def test_stops_after_whole_request_even_if_agent_recovers(monkeypatch, tmp_path, settings):
    calls = retry_models(monkeypatch, chat_request(), [composition(excluded_steps=[]), composition()])
    destination = tmp_path / 'recovered'
    report = asyncio.run(runner.run(destination, max_attempts=3))
    assert report['status'] == 'captured' and report['started'] == report['finished'] == 1
    assert report['validation_failures'] == 1 and len(calls) == 2
    assert report['requests'][0]['outcome'] == 'success'
    assert len(events(destination)) == 2
    snapshot = diag.ValidationSnapshot.model_validate_json((destination / 'failure-001.json').read_text())
    assert snapshot.generation_attempt == 1 and snapshot.violation.rule == 'catalog_partition'
    assert json.loads((destination / 'replay-001.json').read_text())['reproduced']
    assert all('private-sampler-key' not in p.read_text() for p in destination.iterdir() if p.is_file())
    original = (destination / 'session.json').read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(runner.run(destination, max_attempts=3))
    assert (destination / 'session.json').read_bytes() == original


def test_limit_is_reported_without_retrying_until_failure(monkeypatch, tmp_path, settings):
    calls = retry_models(monkeypatch, chat_request(), [composition(), composition()])
    destination = tmp_path / 'no-failure'
    report = asyncio.run(runner.run(destination, max_attempts=2))
    assert report['status'] == 'limit_reached' and report['started'] == report['finished'] == 2
    assert report['validation_failures'] == 0 and not report['snapshots'] and len(calls) == 2
    assert all(r['outcome'] == 'success' for r in report['requests'])
    assert len(events(destination)) == 4


def test_configuration_error_stops_with_no_provider_body(monkeypatch, tmp_path, settings):
    async def broken(*args, **kwargs):
        raise AIConfigError('private-provider-body')

    monkeypatch.setattr(agent_graph, 'call_agent_model', broken)
    destination = tmp_path / 'configuration'
    report = asyncio.run(runner.run(destination))
    assert report['status'] == 'stopped_configuration_error' and report['finished'] == 1
    assert report['validation_failures'] == 0 and len(events(destination)) == 2
    assert 'private-provider-body' not in (destination / 'attempts.jsonl').read_text()


def test_capture_error_is_not_reported_as_missing_real_failure(monkeypatch, tmp_path, settings):
    retry_models(monkeypatch, chat_request(), [composition(excluded_steps=[])])

    def broken(**kwargs):
        raise ValueError('private-capture-error')

    monkeypatch.setattr(diag, 'ValidationSnapshot', broken)
    destination = tmp_path / 'capture-error'
    report = asyncio.run(runner.run(destination))
    assert report['status'] == 'capture_error' and report['finished'] == 1
    assert report['requests'][0]['generation_status'] == 'failed'
    assert report['requests'][0]['capture_errors'] == ['ValueError']
    assert report['validation_failures'] == 0


def test_cancelled_session_keeps_final_interruption_record(monkeypatch, tmp_path, settings):
    destination = tmp_path / 'cancelled'

    async def scenario():
        entered = asyncio.Event()

        async def waiting(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(agent_graph, 'call_agent_model', waiting)
        task = asyncio.create_task(runner.run(destination))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    report = json.loads((destination / 'session.json').read_text())
    assert report['status'] == 'interrupted' and report['started'] == report['finished'] == 1
    assert events(destination)[-1]['outcome'] == 'interrupted'


def test_dry_run_has_no_settings_and_rejects_more_than_ten(monkeypatch):
    def forbidden():
        pytest.fail('dry-run에서 설정을 읽으면 안 됩니다')

    monkeypatch.setattr(runner, 'AISettings', forbidden)
    monkeypatch.setattr('sys.argv', ['capture_planning_validation', '--dry-run'])
    assert runner.main() == 0
    with pytest.raises(ValueError):
        runner.prepare(runner.check.DEFAULT_FIXTURE, 11)
