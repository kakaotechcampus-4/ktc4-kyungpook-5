"""#239: 합성 인원 변경 채팅을 최대 10요청 실행해 첫 검증 실패 자료를 확보한다."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from app.ai.config import AISettings
from app.ai.scripts import check_planning_generation_requests as check
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, now, write_manifest
from app.ai.scripts.planning_latency_inputs import request_hashes
from app.ai.scripts.planning_latency_observation import install_observers
from app.ai.scripts.planning_validation_diagnostics import capture_validation_failures, validator_source, write_snapshot
from app.ai.scripts.replay_planning_validation import replay_file


def prepare(fixture_path, max_attempts):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise ValueError('수집은 1~10개 공개 요청으로 제한합니다')
    raw = fixture_path.read_bytes()
    return raw, check.validate_fixture(json.loads(raw))


async def run(directory, *, fixture_path=check.DEFAULT_FIXTURE, max_attempts=10):
    raw, fixture = prepare(fixture_path, max_attempts)
    settings = AISettings()
    settings.require_api()
    source = validator_source()
    run_id = directory.name
    report = dict(report_version=1, status='running', started_at=now(), run_id=run_id,
        scope='synthetic_planning_validation', purpose='capture_first_validation_failure',
        max_attempts=max_attempts, started=0, finished=0, validation_failures=0, requests=[], snapshots=[],
        stop_policy='최초 온전한 실패 자료를 확보한 공개 요청을 끝까지 처리한 뒤 중단. 성공률 평가 아님.',
        environment=execution_metadata('real_model', settings), validator_source=source.model_dump(),
        diagnostics_sha256={name: hashlib.sha256((check.AI_DIR / 'scripts' / name).read_bytes()).hexdigest()
                            for name in ('capture_planning_validation.py', 'planning_validation_diagnostics.py',
                                         'replay_planning_validation.py', 'check_planning_generation_requests.py')},
        fixture_sha256=hashlib.sha256(raw).hexdigest(),
        profile=dict(case_id='changed_headcount', route='chat', concurrency=1, request_timeout_seconds=180,
                     interval_seconds=0.5))
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'fixture.json').write_bytes(raw)
    write_manifest(directory, report)
    try:
        with (directory / 'attempts.jsonl').open('x') as stream:
            for number in range(1, max_attempts + 1):
                request = check.make_request(fixture, 'changed_headcount', 'chat', f'{run_id}-{number:02d}')
                identity = dict(attempt_id=request.request_id, number=number, case_id='changed_headcount', route='chat')
                append_event(stream, dict(event='started', started_at=now(), **identity,
                    **request_hashes(request), request=request.model_dump(mode='json')))
                report['started'] += 1
                write_manifest(directory, report)
                # 수집기를 바깥에 두면 검증 구간 ID가 활성화된 안쪽에서 원래 예외를 관찰한다.
                with capture_validation_failures(request, run_id=run_id, model=settings.model, source=source) as capture, \
                     install_observers():
                    row, interrupted = await check.attempt(request)
                files, replays = [], []
                for snapshot in capture.snapshots:
                    index = len(report['snapshots']) + 1
                    filename, replay_name = f'failure-{index:03d}.json', f'replay-{index:03d}.json'
                    write_snapshot(directory / filename, snapshot)
                    replay = replay_file(directory / filename, directory / replay_name)
                    report['snapshots'].append(dict(file=filename, replay_file=replay_name,
                        request_id=snapshot.request_id, generation_attempt=snapshot.generation_attempt,
                        rule=snapshot.violation.rule,
                        sha256=hashlib.sha256((directory / filename).read_bytes()).hexdigest()))
                    files.append(filename)
                    replays.append(replay['reproduced'] and replay['same_validator_source'])
                row.update(identity, validation_files=files, capture_errors=capture.errors,
                           validation_rules=[s.violation.rule for s in capture.snapshots])
                append_event(stream, dict(event='finished', finished_at=now(), **row))
                report['finished'] += 1
                report['validation_failures'] += len(files)
                report['requests'].append({k: row.get(k) for k in (
                    'attempt_id', 'outcome', 'generation_entered', 'generation_status',
                    'stale_offer_id_used', 'validation_files', 'validation_rules', 'capture_errors')})
                write_manifest(directory, report)
                print(f'{request.request_id}: {row["outcome"]}, validation_rules={row["validation_rules"]}', flush=True)
                if interrupted:
                    raise asyncio.CancelledError
                if capture.errors:
                    report['status'] = 'capture_error'
                    break
                if files:
                    report['status'] = 'captured' if all(replays) else 'replay_mismatch'
                    break
                if row.get('stop_session'):
                    report['status'] = 'stopped_' + row['stop_session']
                    break
                if number < max_attempts:
                    await asyncio.sleep(0.5)
            else:
                report['status'] = 'limit_reached'
    except (asyncio.CancelledError, KeyboardInterrupt):
        report['status'] = 'interrupted'
        raise
    except BaseException:
        report['status'] = 'runner_failed'
        raise
    finally:
        report['finished_at'] = now()
        write_manifest(directory, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=check.DEFAULT_FIXTURE)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--max-attempts', type=int, default=10)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.dry_run:
            raw, _ = prepare(args.fixture, args.max_attempts)
            print(json.dumps(dict(provider_calls=0, fixture_sha256=hashlib.sha256(raw).hexdigest(),
                max_attempts=args.max_attempts, case_id='changed_headcount', route='chat'), ensure_ascii=False))
            return 0
        if args.output_dir is None:
            parser.error('--output-dir가 필요합니다')
        report = asyncio.run(run(args.output_dir, fixture_path=args.fixture, max_attempts=args.max_attempts))
        print(json.dumps({k: report[k] for k in ('status', 'started', 'finished', 'validation_failures')}, ensure_ascii=False))
        return 0 if report['status'] == 'captured' else 2 if report['status'] == 'limit_reached' else 1
    except (asyncio.CancelledError, KeyboardInterrupt):
        print('수집 중단 상태와 원본 기록을 보존했습니다.')
        return 130
    except Exception as error:
        print(f'수집 오류: {type(error).__name__}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
