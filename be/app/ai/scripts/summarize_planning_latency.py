"""#196: 저장된 P1 측정 파일을 검증하고 집계한다. 모델과 API 설정을 사용하지 않는다."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from app.ai.scripts.planning_latency_inputs import CASE_IDS, LatencyFixture, digest, make_request, request_hashes, schedule
from app.ai.scripts.planning_latency_summary import summarize_group
from app.ai.scripts.planning_latency_observation import OBSERVATION_SCOPE, validate_observation

IDENTITY = ('attempt_id', 'phase', 'round', 'case_id', 'request_sha256', 'normalized_input_sha256')
ENVIRONMENT = ('mode', 'model', 'model_options', 'python', 'platform', 'dependencies', 'source_sha256')
PROFILE = ('rounds', 'warmup', 'interval_seconds', 'concurrency', 'reference_date', 'timezone')


class RecordError(ValueError):
    """원본 내용을 출력하지 않고 불일치한 기록의 종류만 알려준다."""


def require(condition, message):
    if not condition:
        raise RecordError(message)


def identity(item):
    require(isinstance(item, dict), '요청 기록은 객체여야 합니다')
    require(isinstance(item.get('attempt_id'), str) and item['attempt_id'], '요청 ID가 필요합니다')
    require(item.get('phase') in ('warmup', 'measurement') and item.get('case_id') in CASE_IDS,
            '요청 단계 또는 사례가 유효하지 않습니다')
    require(type(item.get('round')) is int and item['round'] >= 0, '라운드가 유효하지 않습니다')
    for key in ('request_sha256', 'normalized_input_sha256'):
        require(isinstance(item.get(key), str) and re.fullmatch(r'[0-9a-f]{64}', item[key]), '요청 해시가 유효하지 않습니다')
    return {key: item[key] for key in IDENTITY}


def read_events(raw):
    events, truncated_tail = [], False
    lines = raw.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError) as error:
            # 강제 종료 때 마지막 한 줄이 덜 쓰일 수 있다. 중간의 손상은 숨기지 않는다.
            if index == len(lines) - 1 and not line.endswith(b'\n'):
                truncated_tail = True
                break
            raise RecordError('JSONL 중간에 읽을 수 없는 기록이 있습니다') from error
        require(isinstance(event, dict), '이벤트는 객체여야 합니다')
        events.append(event)
    return events, truncated_tail


def validate_finished(item, report_version=1):
    require(item.get('outcome') in ('success', 'failed', 'interrupted'), '종료 결과가 유효하지 않습니다')
    value = item.get('ai_request_ms')
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0, '요청 시간이 유효하지 않습니다')
    require(type(item.get('returned_normally')) is bool, '정상 반환 여부가 필요합니다')
    checks = item.get('checks')
    if checks is not None:
        require(isinstance(checks, dict) and all(type(value) is bool for value in checks.values()),
                '검사 결과는 참/거짓 값이어야 합니다')
    if item['outcome'] == 'success':
        require(item['returned_normally'] and checks and all(checks.values()) and item.get('failure') is None,
                '성공 표시와 실제 검사 결과가 다릅니다')
    elif item['outcome'] == 'failed':
        failure = item.get('failure')
        require(isinstance(failure, dict) and isinstance(failure.get('category'), str) and failure['category'],
                '실패 유형이 필요합니다')
    else:
        require(not item['returned_normally'], '중단 요청은 정상 반환이 아닙니다')
    if report_version == 2:
        try:
            validate_observation(item.get('observation'), item['ai_request_ms'], allow_pending=item['outcome'] != 'success')
        except (ValueError, KeyError, TypeError) as error:
            raise RecordError('구간 관측 기록이 유효하지 않습니다') from error
        failure = item.get('failure') or {}
        if 'span_id' in failure:
            origin = next((span for span in item['observation']['spans'] if span['id'] == failure['span_id']), None)
            require(origin is not None and origin['stage'] == failure.get('stage')
                    and origin['failure_code'] == failure['category'], '실패 원인과 구간 기록이 다릅니다')
    else:
        require('observation' not in item, '구간 관측은 세션 형식 2가 필요합니다')


def load_session(directory: Path) -> dict:
    files = {name: (directory / name).read_bytes() for name in ('session.json', 'fixture.json', 'attempts.jsonl')}
    manifest = json.loads(files['session.json'])
    require(isinstance(manifest, dict) and type(manifest.get('report_version')) is int
            and manifest['report_version'] in (1, 2), '지원하지 않는 세션 형식입니다')
    require(isinstance(manifest.get('session_id'), str)
            and re.fullmatch(r'[A-Za-z0-9_-]{1,48}', manifest['session_id']), '세션 ID가 유효하지 않습니다')
    require(manifest.get('status') in ('running', 'completed', 'interrupted', 'runner_failed'), '세션 상태가 유효하지 않습니다')
    fixture = LatencyFixture.model_validate_json(files['fixture.json'])
    require(manifest.get('fixture_sha256') == hashlib.sha256(files['fixture.json']).hexdigest()
            and manifest.get('fixture_version') == fixture.fixture_version, '고정 입력 해시 또는 버전이 다릅니다')
    profile, environment = manifest.get('profile'), manifest.get('environment')
    require(isinstance(profile, dict) and set(PROFILE) <= profile.keys(), '실행 프로필이 필요합니다')
    require(type(profile['warmup']) is bool and type(profile['concurrency']) is int and profile['concurrency'] == 1,
            '지원하지 않는 반복 설정입니다')
    require(type(profile['interval_seconds']) in (int, float)
            and math.isfinite(profile['interval_seconds']) and profile['interval_seconds'] >= 0, '요청 간 대기가 유효하지 않습니다')
    require(profile['reference_date'] == fixture.reference_date and profile['timezone'] == fixture.timezone,
            '기준일 또는 시간대가 고정 입력과 다릅니다')
    expected_order = schedule(fixture, profile['rounds'], profile['warmup'])
    require(isinstance(environment, dict) and set(ENVIRONMENT) <= environment.keys(), '환경 정보가 필요합니다')
    require(environment['mode'] in ('real_model', 'injected_callers')
            and isinstance(environment['source_sha256'], dict) and environment['source_sha256']
            and isinstance(environment['dependencies'], dict) and environment['dependencies'], '환경 관측 범위가 유효하지 않습니다')
    if environment['mode'] == 'real_model':
        require(isinstance(environment['model'], str) and environment['model']
                and isinstance(environment['model_options'], dict) and environment['model_options'],
                '실제 모델의 설정 정보가 필요합니다')
    if manifest['report_version'] == 2:
        require(isinstance(environment.get('coverage'), dict)
                and environment['coverage'].get('stage_timings') == OBSERVATION_SCOPE, '구간 관측 범위 정보가 필요합니다')
    planned = manifest.get('planned_attempts')
    require(isinstance(planned, list) and len(planned) == len(expected_order), '예정 요청 수가 다릅니다')
    planned = [identity(item) for item in planned]
    require(len({item['attempt_id'] for item in planned}) == len(planned), '예정 요청 ID가 중복되었습니다')
    require([(item['phase'], item['round'], item['case_id']) for item in planned] == [
        (phase, number, case.id) for phase, number, case in expected_order], '예정 실행 순서가 다릅니다')
    by_case = {case.id: case for case in fixture.cases}
    for item in planned:
        expected_hashes = request_hashes(make_request(fixture, by_case[item['case_id']], item['attempt_id']))
        require(expected_hashes == {key: item[key] for key in expected_hashes}, '고정 입력과 예정 요청이 다릅니다')
    normalized_inputs = {}
    for case_id in CASE_IDS:
        hashes = {item['normalized_input_sha256'] for item in planned if item['case_id'] == case_id}
        require(len(hashes) == 1, '같은 사례의 출발 입력이 다릅니다')
        normalized_inputs[case_id] = next(iter(hashes))

    events, truncated_tail = read_events(files['attempts.jsonl'])
    started, finished, active = [], [], None
    for item in events:
        key = identity(item)
        if item.get('event') == 'started':
            require(active is None and len(started) < len(planned), '중복 또는 순서가 어긋난 시작 기록입니다')
            require(key == planned[len(started)], '시작 기록이 예정 요청과 다릅니다')
            request = item.get('request')
            require(isinstance(request, dict), '시작 기록에 실제 요청이 필요합니다')
            require(request_hashes(request) == {field: key[field] for field in ('request_sha256', 'normalized_input_sha256')},
                    '실제 요청과 해시가 다릅니다')
            active = key
            started.append(item)
        elif item.get('event') == 'finished':
            require(active is not None and key == active, '중복 또는 대응하지 않는 종료 기록입니다')
            validate_finished(item, manifest['report_version'])
            finished.append(item)
            active = None
        else:
            raise RecordError('알 수 없는 이벤트입니다')

    counts = {phase: dict(started=sum(item['phase'] == phase for item in started),
                         finished=sum(item['phase'] == phase for item in finished),
                         **{outcome: sum(item['phase'] == phase and item['outcome'] == outcome for item in finished)
                            for outcome in ('success', 'failed', 'interrupted')}) for phase in ('warmup', 'measurement')}
    if manifest['status'] == 'completed':
        require(manifest.get('counts') == counts, '세션 건수와 원본 이벤트가 다릅니다')
    complete = (manifest['status'] == 'completed' and len(finished) == len(planned)
                and not truncated_tail and all(item['outcome'] != 'interrupted' for item in finished))
    return dict(manifest=manifest, planned=planned, started=started, finished=finished, complete=complete,
                truncated_tail=truncated_tail, normalized_inputs=normalized_inputs,
                source_sha256={name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()})


def configuration(session):
    manifest = session['manifest']
    return dict(report_version=manifest['report_version'], observation_scope=manifest['environment'].get('coverage'),
                fixture_sha256=manifest['fixture_sha256'], fixture_version=manifest['fixture_version'],
                profile={key: manifest['profile'][key] for key in PROFILE},
                environment={key: manifest['environment'][key] for key in ENVIRONMENT},
                normalized_inputs=session['normalized_inputs'])


def aggregate_sessions(directories) -> dict:
    require(bool(directories), '집계할 세션이 필요합니다')
    sessions = [load_session(Path(directory)) for directory in directories]
    ids = [item['manifest']['session_id'] for item in sessions]
    require(len(set(ids)) == len(ids), '같은 세션을 중복 집계할 수 없습니다')
    common = configuration(sessions[0])
    require(all(configuration(item) == common for item in sessions), '입력, 프로필 또는 실행 환경이 다른 세션입니다')
    planned = [entry for session in sessions for entry in session['planned']]
    require(len({item['attempt_id'] for item in planned}) == len(planned), '세션 사이에 요청 ID가 중복되었습니다')

    def groups(selected):
        # 각 세션의 p95를 평균 내지 않고 원본 표본을 모은다.
        return {phase: {case: summarize_group(*[
            [item for session in selected for item in session[kind] if item['phase'] == phase and item['case_id'] == case]
            for kind in ('planned', 'started', 'finished')]) for case in CASE_IDS}
            for phase in ('warmup', 'measurement')}

    def source(session):
        return dict(session_id=session['manifest']['session_id'], status=session['manifest']['status'],
                    complete=session['complete'], truncated_tail=session['truncated_tail'],
                    source_sha256=session['source_sha256'], groups=groups([session]))

    observation_complete = None
    if common['report_version'] == 2 and any(session['started'] for session in sessions):
        observation_complete = all(len(session['finished']) == len(session['started'])
                                   and all(item['observation']['complete'] for item in session['finished'])
                                   for session in sessions)

    return dict(summary_version=2, percentile_method='linear_R7', units='milliseconds',
                complete=all(session['complete'] for session in sessions), session_count=len(sessions),
                observation_complete=observation_complete,
                mode=common['environment']['mode'], model=common['environment']['model'],
                profile=common['profile'], configuration_sha256=digest(common),
                aggregation_source_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                           for path in (Path(__file__), *[Path(__file__).with_name(name) for name in (
                                               'planning_latency_summary.py', 'planning_latency_observation.py', 'planning_latency_inputs.py')])},
                coverage=dict(timing='public_function_with_nested_spans' if common['report_version'] == 2 else 'public_function_only',
                              stage_timings=OBSERVATION_SCOPE if common['report_version'] == 2 else None,
                              model_call_attempts='wrapped_invoker_attempts' if common['report_version'] == 2 else None,
                              http_attempts=None, token_usage=None),
                groups=groups(sessions), sessions=[source(session) for session in sessions])


def render_table(summary) -> str:
    observation = summary.get('observation_complete')
    scope = '미관측' if observation is None else '완료' if observation else '부분 관측'
    lines = [f"모드: {summary['mode']}, 세션: {summary['session_count']}, 기록: {'완료' if summary['complete'] else '부분 결과'}, 구간: {scope}",
             '사례 | 시작 | 성공 | 실패 | 미완료 | 미시작 | 성공률 | 성공 p50(ms) | 성공 p95(ms)']
    for case_id, group in summary['groups']['measurement'].items():
        counts = group['counts']
        rate = f"{group['success_rate']:.1%}" if group['success_rate'] is not None else '-'
        times = ['-' if group['success_ms'][key] is None else f"{group['success_ms'][key]:.3f}" for key in ('p50_ms', 'p95_ms')]
        lines.append(' | '.join(map(str, [case_id, counts['started'], counts['success'], counts['failed'],
                                         counts['pending'] + counts['interrupted'], counts['not_started'], rate, *times])))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = aggregate_sessions(args.sessions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        print(render_table(summary))
        return 0 if summary['complete'] and summary['observation_complete'] is not False else 2
    except RecordError as error:
        print(f'집계 실패: {error}')
    except Exception as error:
        print(f'집계 실패: {type(error).__name__}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
