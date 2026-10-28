"""#196: 고정 입력으로 P1 공개 함수 한 세션을 순차 반복한다. --dry-run은 모델을 호출하지 않는다."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ai import chat_planning, generate_planning_preview, PlanningPublicResult
from app.ai.config import AISettings
from app.ai.scripts.planning_latency_checks import inspect_result
from app.ai.scripts.planning_latency_observation import (
    OBSERVATION_SCOPE, capture_request, error_category, install_observers,
)
from app.ai.scripts.planning_latency_inputs import (
    AI_DIR, DEFAULT_FIXTURE, LatencyFixture, json_text, make_request, request_hashes, schedule,
)


def now() -> str:
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def prepare(fixture_path, session_id, rounds, warmup, interval):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', session_id):
        raise ValueError('session_id는 영문, 숫자, 밑줄, 하이픈 1~48자로 지정합니다')
    if not math.isfinite(interval) or interval < 0:
        raise ValueError('요청 간 대기는 0 이상 유한한 값이어야 합니다')
    raw = fixture_path.read_bytes()
    fixture = LatencyFixture.model_validate_json(raw)
    plan = schedule(fixture, rounds, warmup)
    attempts = []
    for phase, number, case in plan:
        attempt_id = f'{session_id}-{phase}-{number:04d}-{case.id}'
        request = make_request(fixture, case, attempt_id)
        attempts.append(dict(attempt_id=attempt_id, phase=phase, round=number, case_id=case.id,
                             **request_hashes(request)))
    return raw, fixture, plan, attempts


def execution_metadata(mode, settings):
    from app.ai.llm import DEFAULT_MAX_RETRIES
    from app.ai.features.planning.generation.model import PLAN_MAX_OUTPUT_TOKENS
    sources = [AI_DIR / name for name in ('__init__.py', 'contracts.py', 'facade.py', 'ports.py',
                                        'config.py', 'llm.py', 'errors.py', 'planning_catalog.py')
               if (AI_DIR / name).exists()]
    sources += sorted((AI_DIR / 'features/planning').rglob('*.py'))
    sources += sorted((AI_DIR / 'features/planning').rglob('*.md'))
    sources += [Path(__file__), AI_DIR / 'scripts/planning_latency_inputs.py',
                AI_DIR / 'scripts/planning_latency_checks.py', AI_DIR / 'scripts/planning_latency_observation.py']
    versions = {name: importlib.metadata.version(name) for name in ('langgraph', 'langchain-openai', 'pydantic', 'openai')}
    return dict(
        mode=mode, python=platform.python_version(), platform=platform.platform(), dependencies=versions,
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True)),
        source_sha256={str(path.relative_to(AI_DIR)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        # AISettings 전체를 dump하지 않는다. 주소, 키, 헤더는 기록 대상이 아니다.
        model=settings.model if settings else None,
        model_options=dict(temperature='not_set', reasoning='not_set', sdk_max_retries=DEFAULT_MAX_RETRIES,
                           request_timeout_seconds=settings.request_timeout_seconds if settings else None,
                           generation_max_tokens=PLAN_MAX_OUTPUT_TOKENS, generation_streaming=True) if settings else None,
        coverage=dict(timing='public_function_with_nested_spans', stage_timings=OBSERVATION_SCOPE,
                      model_call_attempts='wrapped_invoker_attempts',
                      http_attempts=None, token_usage=None, model_input_chars=None,
                      unavailable_reason='SDK 내부 HTTP 시도와 토큰은 미관측. 구간의 메시지 문자 수는 text만 포함'),
    )


def write_manifest(directory, report):
    temporary = directory / '.session.tmp'
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(directory / 'session.json')


def append_event(stream, event):
    stream.write(json_text(event) + '\n')
    stream.flush()
    os.fsync(stream.fileno())


async def measure_attempt(case, request, call, *, clock=time.perf_counter_ns):
    original_json = request.model_dump_json()
    caught, interrupted = None, False
    with capture_request(clock) as trace:
        started = clock()
        trace.origin_ns = started
        try:
            result = await call(request)
        except (asyncio.CancelledError, KeyboardInterrupt):
            interrupted = True
        except Exception as error:
            caught = error
        finally:
            elapsed = (clock() - started) / 1_000_000
    # 이 시점 이후의 계약 검사/파일 기록은 구간과 전체 시간 양쪽에서 제외한다.
    timing = dict(ai_request_ms=elapsed, observation=trace.snapshot(elapsed))
    if interrupted:
        return dict(outcome='interrupted', returned_normally=False, **timing), True
    if caught is not None:
        origin = trace.origin_for(caught)
        failure = dict(category=error_category(caught), error_type=type(caught).__name__)
        if origin:
            failure.update(stage=origin['stage'], span_id=origin['id'])
        return dict(outcome='failed', returned_normally=False, failure=failure, **timing), False
    try:
        # 모델을 우회한 테스트 호출자도 공개 결과 계약을 통과해야 한다.
        parsed = PlanningPublicResult.model_validate_json(
            PlanningPublicResult.model_validate(result).model_dump_json())
        original = type(request).model_validate_json(original_json)
        inspected = inspect_result(case, original, parsed)
        inspected['checks']['request_unchanged'] = request.model_dump_json() == original_json
        passed = all(inspected['checks'].values())
        generation = parsed.view.generation_result
        category = (f'generation_{generation.status}' if generation and generation.status != 'generated'
                    else 'expectation_failed')
        failure = None if passed else dict(category=category, error_type=None)
        origin = trace.generation_failure() if generation and generation.status == 'failed' else None
        if failure is not None and origin:
            failure.update(category=origin['failure_code'], error_type=origin['error_type'],
                           stage=origin['stage'], span_id=origin['id'])
        return dict(outcome='success' if passed else 'failed', returned_normally=True, **timing,
                    failure=failure,
                    **inspected, result=parsed.model_dump(mode='json')), False
    except Exception as error:
        return dict(outcome='failed', returned_normally=True, **timing,
                    failure=dict(category=error_category(error), error_type=type(error).__name__)), False


async def run_session(output_dir: Path, *, session_id: str, fixture_path=DEFAULT_FIXTURE,
                      rounds=10, warmup=True, interval=1.0, chat=None, generate=None,
                      clock=time.perf_counter_ns, sleep=asyncio.sleep) -> dict:
    raw, fixture, plan, attempts = prepare(fixture_path, session_id, rounds, warmup, interval)
    if (chat is None) != (generate is None):
        raise ValueError('테스트 호출자는 채팅과 버튼을 함께 지정해야 합니다')
    injected = chat is not None
    settings = None if injected else AISettings()
    if settings:
        settings.require_api()
    chat = chat if injected else chat_planning
    generate = generate if injected else generate_planning_preview
    report = dict(
        report_version=2, session_id=session_id, status='running', started_at=now(),
        fixture_sha256=hashlib.sha256(raw).hexdigest(), fixture_version=fixture.fixture_version,
        profile=dict(rounds=rounds, warmup=warmup, interval_seconds=interval, concurrency=1,
                     reference_date=fixture.reference_date, timezone=fixture.timezone),
        environment=execution_metadata('injected_callers' if injected else 'real_model', settings),
        planned_attempts=attempts, counts={phase: dict(started=0, finished=0, success=0, failed=0, interrupted=0)
                                         for phase in ('warmup', 'measurement')},
    )
    # 기존 결과를 덮어쓰지 않는다. 폴더 생성부터 배타적으로 확보한다.
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'fixture.json').write_bytes(raw)
    write_manifest(output_dir, report)
    try:
        with install_observers(), (output_dir / 'attempts.jsonl').open('x') as stream:
            for index, ((phase, number, case), entry) in enumerate(zip(plan, attempts, strict=True)):
                request = make_request(fixture, case, entry['attempt_id'])
                call = generate if case.id == 'G2' else chat
                count = report['counts'][phase]
                request_data = request.model_dump(mode='json')
                append_event(stream, dict(event='started', started_at=now(), **entry,
                                          request=request_data, request_bytes=len(json_text(request_data).encode()),
                                          user_message_chars=len(request_data.get('message', {}).get('content', '')),
                                          history_count=len(request.resume_state.payload.history)))
                count['started'] += 1
                # 매번 새 요청을 넘긴다. 반환 next_state를 다음 반복의 입력으로 쓰지 않는다.
                measured, interrupted = await measure_attempt(case, request, call, clock=clock)
                append_event(stream, dict(event='finished', finished_at=now(), **entry, **measured))
                count['finished'] += 1
                count[measured['outcome']] += 1
                write_manifest(output_dir, report)
                if interrupted:
                    raise asyncio.CancelledError
                if index + 1 < len(plan):
                    await sleep(interval)
        report['status'] = 'completed'
    except (asyncio.CancelledError, KeyboardInterrupt):
        report['status'] = 'interrupted'
        raise
    except BaseException:
        report['status'] = 'runner_failed'
        raise
    finally:
        report['finished_at'] = now()
        write_manifest(output_dir, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--interval-seconds', type=float, default=1.0)
    parser.add_argument('--no-warmup', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.dry_run:
            raw, _, _, attempts = prepare(args.fixture, args.session_id, args.rounds,
                                         not args.no_warmup, args.interval_seconds)
            print(json.dumps(dict(mode='dry_run', fixture_sha256=hashlib.sha256(raw).hexdigest(),
                                  attempts=attempts), ensure_ascii=False, indent=2))
            return 0
        if args.output_dir is None:
            parser.error('--output-dir가 필요합니다')
        report = asyncio.run(run_session(args.output_dir, session_id=args.session_id, fixture_path=args.fixture,
                                        rounds=args.rounds, warmup=not args.no_warmup, interval=args.interval_seconds))
        print(json.dumps(dict(status=report['status'], counts=report['counts']), ensure_ascii=False))
        return 1 if any(group['failed'] for group in report['counts'].values()) else 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        print('측정을 중단했습니다. 시작/종료 기록과 세션 상태를 확인해 주세요.')
        return 130
    except Exception as error:
        # 예외 원문이나 공급자 응답을 콘솔에 노출하지 않는다.
        print(f'측정 실행 실패: {type(error).__name__}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
