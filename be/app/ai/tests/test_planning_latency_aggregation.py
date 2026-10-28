"""#196: 원본 파일의 성공/실패/부분 기록을 알려진 정답으로 집계한다."""

import asyncio
import hashlib
import json

import pytest

from app.ai import AITimeoutError, chat_planning, generate_planning_preview
from app.ai.scripts import summarize_planning_latency as aggregate
from app.ai.scripts import measure_planning_latency as runner
from app.ai.scripts.planning_latency_inputs import DEFAULT_FIXTURE, make_request, request_hashes
from app.ai.tests.test_planning_latency_runner import fixed_models  # noqa: F401


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def write_session(directory, *, session_id='known-01', observations=None, warmup=True):
    """계산용 합성 기록. 예상 시간과 결과를 직접 지정하며 성능 측정으로 쓰지 않는다."""
    observations = observations or [('success', value) for value in (2000, 3000, 4000, 5000, 6000)]
    raw, fixture, plan, attempts = runner.prepare(DEFAULT_FIXTURE, session_id, len(observations), warmup, 1)
    directory.mkdir()
    (directory / 'fixture.json').write_bytes(raw)
    counts = {phase: dict(started=0, finished=0, success=0, failed=0, interrupted=0) for phase in ('warmup', 'measurement')}
    rows = []
    for (phase, number, case), entry in zip(plan, attempts, strict=True):
        request = make_request(fixture, case, entry['attempt_id'])
        outcome, elapsed = ('success', 999999) if phase == 'warmup' else observations[number - 1]
        rows.append(dict(event='started', request=request.model_dump(mode='json'), **entry))
        rows.append(dict(event='finished', outcome=outcome, ai_request_ms=elapsed,
                         returned_normally=outcome == 'success', checks=dict(fixed_expectation=outcome == 'success'),
                         failure=None if outcome == 'success' else dict(category='timeout'), **entry))
        counts[phase]['started'] += 1
        counts[phase]['finished'] += 1
        counts[phase][outcome] += 1
    manifest = dict(report_version=1, session_id=session_id, status='completed', fixture_version=1,
                    fixture_sha256=hashlib.sha256(raw).hexdigest(),
                    profile=dict(rounds=len(observations), warmup=warmup, interval_seconds=1,
                                 concurrency=1, reference_date=fixture.reference_date, timezone=fixture.timezone),
                    environment=dict(mode='injected_callers', model=None, model_options=None,
                                     python='fixed-test', platform='fixed-test', dependencies={'test': 'fixed'},
                                     source_sha256={'test.py': '0' * 64}), planned_attempts=attempts, counts=counts)
    write_json(directory / 'session.json', manifest)
    rewrite_rows(directory, rows)
    return directory


def read_rows(directory):
    return [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]


def rewrite_rows(directory, rows):
    (directory / 'attempts.jsonl').write_text(''.join(json.dumps(item) + '\n' for item in rows))


def set_status(directory, status):
    path = directory / 'session.json'
    data = json.loads(path.read_text())
    data['status'] = status
    write_json(path, data)


def test_known_times_exclude_warmup_and_separate_failures(tmp_path):
    observations = [('success', value) for value in (2000, 3000, 4000, 5000, 6000)] + [('failed', 90000)]
    source = write_session(tmp_path / 'source', observations=observations)
    summary = aggregate.aggregate_sessions([source])
    measured = summary['groups']['measurement']['C1']
    assert measured['counts']['started'] == 6
    assert measured['success_rate'] == pytest.approx(5 / 6)
    assert measured['success_ms'] == dict(n=5, p50_ms=4000, p95_ms=5800, mean_ms=4000, max_ms=6000)
    assert measured['failure_ms']['n'] == 1 and measured['failure_ms']['max_ms'] == 90000
    assert measured['failures_by_category']['timeout']['n'] == 1
    assert summary['groups']['warmup']['C1']['success_ms']['max_ms'] == 999999
    assert summary['complete'] and summary['units'] == 'milliseconds'


def test_pooled_percentiles_are_recomputed_from_raw_samples(tmp_path):
    first = write_session(tmp_path / 'first', session_id='s1',
                          observations=[('success', 1), ('failed', 100), ('failed', 100)])
    second = write_session(tmp_path / 'second', session_id='s2',
                           observations=[('success', 10), ('success', 20), ('success', 30)])
    summary = aggregate.aggregate_sessions([first, second])
    pooled = summary['groups']['measurement']['C1']
    assert pooled['success_ms']['n'] == 4
    assert pooled['success_ms']['p95_ms'] == pytest.approx(28.5)
    assert pooled['success_ms']['p50_ms'] == 15
    per_session = [item['groups']['measurement']['C1']['success_ms']['p95_ms'] for item in summary['sessions']]
    assert per_session == [1, 29]
    assert pooled['success_ms']['p95_ms'] != sum(per_session) / 2


def test_three_sessions_match_known_counts_and_percentiles(tmp_path):
    sources = []
    for number in (1, 2, 3):
        observations = [('success', value * 1000) if value <= 28 else ('failed', 90000)
                        for value in range((number - 1) * 10 + 1, number * 10 + 1)]
        sources.append(write_session(tmp_path / f'session-{number}', session_id=f'known-{number}',
                                     observations=observations))
    summary = aggregate.aggregate_sessions(sources)
    assert summary['session_count'] == 3 and summary['complete']
    for case_id in ('C1', 'C2', 'G1', 'G2'):
        group = summary['groups']['measurement'][case_id]
        assert group['counts']['started'] == 30
        assert group['counts']['success'] == 28 and group['counts']['failed'] == 2
        assert group['success_rate'] == pytest.approx(28 / 30)
        assert group['success_ms']['p50_ms'] == 14500
        assert group['success_ms']['p95_ms'] == pytest.approx(26650)
        assert summary['groups']['warmup'][case_id]['counts']['started'] == 3


def test_missing_finish_is_pending_and_never_a_zero_ms_sample(tmp_path):
    source = write_session(tmp_path / 'pending', observations=[('success', 10)], warmup=False)
    rewrite_rows(source, read_rows(source)[:-1])
    set_status(source, 'running')
    summary = aggregate.aggregate_sessions([source])
    pending = summary['groups']['measurement']['G2']
    assert not summary['complete']
    assert pending['counts']['started'] == pending['counts']['pending'] == 1
    assert pending['success_rate'] == 0
    assert pending['success_ms']['n'] == 0 and pending['success_ms']['p50_ms'] is None


def test_interruption_and_unstarted_requests_remain_visible(tmp_path):
    source = write_session(tmp_path / 'interrupted', observations=[('success', 10)], warmup=False)
    rows = read_rows(source)[:2]
    rows[-1].update(outcome='interrupted', returned_normally=False, checks={}, ai_request_ms=7)
    rewrite_rows(source, rows)
    set_status(source, 'interrupted')
    summary = aggregate.aggregate_sessions([source])
    c1 = summary['groups']['measurement']['C1']
    assert not summary['complete']
    assert c1['counts']['interrupted'] == 1 and c1['completed_ms']['n'] == 0
    assert c1['interrupted_wait_ms']['max_ms'] == 7
    assert summary['groups']['measurement']['C2']['counts']['not_started'] == 1
    assert summary['groups']['measurement']['C2']['success_rate'] is None


def test_last_partial_json_line_is_reported_but_middle_corruption_is_rejected(tmp_path):
    source = write_session(tmp_path / 'truncated', observations=[('success', 10)], warmup=False)
    rewrite_rows(source, read_rows(source)[:-1])
    with (source / 'attempts.jsonl').open('ab') as stream:
        stream.write(b'{"event":"unfinished')
    set_status(source, 'running')
    summary = aggregate.aggregate_sessions([source])
    assert summary['sessions'][0]['truncated_tail'] and not summary['complete']
    assert summary['groups']['measurement']['G2']['counts']['pending'] == 1
    with (source / 'attempts.jsonl').open('ab') as stream:
        stream.write(b'\n{}\n')
    with pytest.raises(aggregate.RecordError, match='JSONL 중간'):
        aggregate.aggregate_sessions([source])


@pytest.mark.parametrize('mutation', ['duplicate_start', 'duplicate_finish', 'orphan_finish', 'wrong_order', 'input_hash', 'changed_input_and_hash', 'false_success'])
def test_invalid_records_are_rejected_instead_of_changing_statistics(tmp_path, mutation):
    source = write_session(tmp_path / mutation, observations=[('success', 10)], warmup=False)
    rows = read_rows(source)
    if mutation == 'duplicate_start':
        rows.insert(1, rows[0])
    elif mutation == 'duplicate_finish':
        rows.insert(2, rows[1])
    elif mutation == 'orphan_finish':
        del rows[0]
    elif mutation == 'wrong_order':
        rows = rows[2:4] + rows[:2] + rows[4:]
    elif mutation == 'input_hash':
        rows[0]['request']['draft']['conditions']['headcount'] = 123
    elif mutation == 'changed_input_and_hash':
        rows[0]['request']['message']['content'] = '다른 질문'
        hashes = request_hashes(rows[0]['request'])
        rows[0].update(hashes)
        rows[1].update(hashes)
        path = source / 'session.json'
        manifest = json.loads(path.read_text())
        manifest['planned_attempts'][0].update(hashes)
        write_json(path, manifest)
    else:
        rows[1]['checks']['fixed_expectation'] = False
    rewrite_rows(source, rows)
    with pytest.raises(aggregate.RecordError):
        aggregate.aggregate_sessions([source])


@pytest.mark.parametrize('elapsed', [-1, float('nan'), float('inf'), True])
def test_invalid_recorded_time_cannot_be_a_statistic(tmp_path, elapsed):
    source = write_session(tmp_path / 'bad-time', observations=[('success', 10)], warmup=False)
    rows = read_rows(source)
    rows[1]['ai_request_ms'] = elapsed
    rewrite_rows(source, rows)
    with pytest.raises(aggregate.RecordError, match='요청 시간'):
        aggregate.aggregate_sessions([source])


def test_duplicate_sessions_and_mismatched_counts_are_rejected(tmp_path):
    source = write_session(tmp_path / 'source')
    with pytest.raises(aggregate.RecordError, match='같은 세션'):
        aggregate.aggregate_sessions([source, source])
    path = source / 'session.json'
    manifest = json.loads(path.read_text())
    manifest['counts']['measurement']['success'] += 1
    write_json(path, manifest)
    with pytest.raises(aggregate.RecordError, match='건수'):
        aggregate.aggregate_sessions([source])


@pytest.mark.parametrize('setting', ['model_mode', 'source_hash', 'interval', 'dependencies'])
def test_incompatible_sessions_are_not_pooled(tmp_path, setting):
    first = write_session(tmp_path / 'first', session_id='s1')
    second = write_session(tmp_path / 'second', session_id='s2')
    path = second / 'session.json'
    data = json.loads(path.read_text())
    if setting == 'model_mode':
        data['environment'].update(mode='real_model', model='test-model', model_options={'temperature': 'not_set'})
    elif setting == 'source_hash':
        data['environment']['source_sha256']['test.py'] = '1' * 64
    elif setting == 'interval':
        data['profile']['interval_seconds'] = 2
    else:
        data['environment']['dependencies']['test'] = 'other'
    write_json(path, data)
    with pytest.raises(aggregate.RecordError, match='다른 세션'):
        aggregate.aggregate_sessions([first, second])


def test_saved_fixture_changes_are_detected(tmp_path):
    source = write_session(tmp_path / 'fixture')
    with (source / 'fixture.json').open('a') as stream:
        stream.write(' ')
    with pytest.raises(aggregate.RecordError, match='입력 해시'):
        aggregate.aggregate_sessions([source])


def test_real_recorder_with_fixed_models_flows_into_aggregator(tmp_path, fixed_models):
    directories = []

    async def chat(request):
        tick[0] += 1_000_000
        if '-0002-C1' in request.request_id:
            raise AITimeoutError('private-provider-body')
        return await chat_planning(request)

    async def button(request):
        tick[0] += 1_000_000
        return await generate_planning_preview(request)

    for index in (1, 2):
        directory = tmp_path / f'session-{index}'
        tick = [0]
        asyncio.run(runner.run_session(directory, session_id=f'fixed-{index}', rounds=2, interval=0,
                    chat=chat, generate=button, clock=lambda: tick[0]))
        directories.append(directory)
    before = [{name: (directory / name).read_bytes() for name in ('session.json', 'fixture.json', 'attempts.jsonl')}
              for directory in directories]
    summary = aggregate.aggregate_sessions(directories)
    c1 = summary['groups']['measurement']['C1']
    assert c1['counts']['started'] == 4 and c1['counts']['success'] == 2 and c1['counts']['failed'] == 2
    assert c1['success_rate'] == .5 and c1['success_ms']['p95_ms'] == 1
    assert c1['failure_ms']['p50_ms'] == 1
    assert summary['groups']['measurement']['G2']['counts']['success'] == 4
    assert summary['groups']['warmup']['C1']['counts']['success'] == 2
    assert summary['complete'] and summary['mode'] == 'injected_callers'
    assert 'private-provider-body' not in json.dumps(summary)
    for directory, snapshots in zip(directories, before, strict=True):
        assert all((directory / name).read_bytes() == data for name, data in snapshots.items())


def test_cli_needs_no_api_settings_and_does_not_overwrite_output(tmp_path, monkeypatch, capsys):
    source = write_session(tmp_path / 'source')
    target = tmp_path / 'summary.json'

    def unexpected():
        pytest.fail('집계는 API 설정을 읽지 않습니다')

    monkeypatch.setattr(runner, 'AISettings', unexpected)
    monkeypatch.setattr('sys.argv', ['summary', '--sessions', str(source), '--output', str(target)])
    assert aggregate.main() == 0
    assert json.loads(target.read_text())['groups']['measurement']['C1']['success_ms']['p50_ms'] == 4000
    original = target.read_bytes()
    assert aggregate.main() == 1
    assert target.read_bytes() == original
    assert 'FileExistsError' in capsys.readouterr().out


def test_partial_cli_writes_provisional_summary_with_distinct_exit_code(tmp_path, monkeypatch):
    source = write_session(tmp_path / 'source', observations=[('success', 10)], warmup=False)
    rewrite_rows(source, read_rows(source)[:-1])
    set_status(source, 'running')
    target = tmp_path / 'partial.json'
    monkeypatch.setattr('sys.argv', ['summary', '--sessions', str(source), '--output', str(target)])
    assert aggregate.main() == 2
    assert json.loads(target.read_text())['complete'] is False
