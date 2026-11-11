"""#269: 실행 문맥 위치(v7: 첫 시스템 메시지 안 / v8: 맨 끝)를 같은 실행 안에서 번갈아 잰다.

지시문, Tool 스키마, 모델 설정은 같고 메시지 순서만 다르다. 한 세션의 순서는 아래와 같다.
  준비 실행   C1, C2, G1을 v7·v8로 한 번씩(집계 제외)
  본측정     라운드마다 사례 순서를 뒤집고(C1→C2→G1 / G1→C2→C1), 사례 안에서 v7·v8 순서도 뒤집는다
  대조 사례   #205의 보류 경계 사례를 v7·v8로 --controls회씩(품질 확인용)
본측정의 성공 판정·구간 시간·토큰 기록은 #263 측정기(measure_attempt)를 그대로 쓴다.

  .venv/bin/python -m app.ai.scripts.compare_agent_context_layout --output-dir <작업 트리 밖 폴더> --session-id s1
"""

import argparse
import asyncio
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import SystemMessage

from app.ai import PlanningPublicResult, chat_planning
from app.ai.config import AISettings
from app.ai.features.planning.agent import nodes
from app.ai.scripts.check_planning_deferrals import CASES as BOUNDARY_CASES, case_request, inspect_boundary
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, measure_attempt, now, write_manifest
from app.ai.scripts.planning_latency_inputs import DEFAULT_FIXTURE, json_text, load_fixture, make_request
from app.ai.scripts.planning_latency_observation import capture_request, error_category, install_observers
from app.ai.scripts.planning_latency_summary import summarize_group

CASE_IDS = ('C1', 'C2', 'G1')  # G2(버튼)는 대화 모델을 부르지 않아 대상에서 뺀다.
VARIANTS = ('v7', 'v8')
# 핵심 입력(generation_only)은 C2와 같은 발화라 본측정에서 이미 잰다.
CONTROLS = tuple(case for case in BOUNDARY_CASES if case.id != 'generation_only')


def legacy_v7_messages(context, messages, *, allow_tools):
    """planning-agent-v7의 메시지 순서. 실행 문맥을 지시문 뒤에 붙여 첫 시스템 메시지 하나로 보낸다."""
    instruction = nodes.PROMPT + "\n\n" + nodes.agent_context_text(context, allow_tools=allow_tools)
    return [SystemMessage(content=instruction), *messages]


LAYOUTS = dict(v7=legacy_v7_messages, v8=nodes.agent_messages)


def schedule(rounds, controls):
    """(phase, round, kind, case_id, variant) 목록. 순서 효과를 줄이려고 사례와 변형 순서를 번갈아 뒤집는다."""
    plan = [('warmup', 0, 'latency', case_id, variant) for case_id in CASE_IDS for variant in VARIANTS]
    for number in range(1, rounds + 1):
        cases = CASE_IDS if number % 2 else tuple(reversed(CASE_IDS))
        variants = VARIANTS if number % 2 else tuple(reversed(VARIANTS))
        plan += [('measurement', number, 'latency', case_id, variant) for case_id in cases for variant in variants]
    for number in range(1, controls + 1):
        variants = VARIANTS if number % 2 else tuple(reversed(VARIANTS))
        plan += [('control', number, 'boundary', case.id, variant) for case in CONTROLS for variant in variants]
    return plan


async def measure_control(case, request, *, keep_result=False):
    """보류 경계 사례 한 건. 성공 판정은 #205 검사기(inspect_boundary)를 그대로 쓴다.

    keep_result=True면 공개 결과 전체(`result`)도 남긴다. 실패한 응답의 Tool 인자를 보려면 필요하다(#274).
    """
    before = request.model_dump_json()
    row = dict(passed=False)
    with capture_request(time.perf_counter_ns) as trace:
        started = time.perf_counter_ns()
        trace.origin_ns = started
        try:
            result = await chat_planning(request)
        except Exception as error:
            row['error'] = error_category(error)
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
    row.update(ai_request_ms=elapsed, observation=trace.snapshot(elapsed))
    if 'error' not in row:
        result = PlanningPublicResult.model_validate_json(result.model_dump_json())
        row.update(inspect_boundary(request, result, case))
        row['checks']['request_unchanged'] = request.model_dump_json() == before
        row['passed'] = all(row['checks'].values())
        if keep_result:
            row['result'] = result.model_dump(mode='json')
    return row


def summarize(rows):
    """변형 × 사례별 집계. 본측정은 #263 집계(summarize_group), 대조 사례는 통과 수와 실패한 검사 이름."""
    latency, controls = {}, {}
    for variant in VARIANTS:
        latency[variant] = {}
        for case_id in CASE_IDS:
            selected = [row for row in rows if row['phase'] == 'measurement'
                        and row['variant'] == variant and row['case_id'] == case_id]
            latency[variant][case_id] = summarize_group(selected, selected, selected)
        controls[variant] = {}
        for case in CONTROLS:
            selected = [row for row in rows if row['phase'] == 'control'
                        and row['variant'] == variant and row['case_id'] == case.id]
            controls[variant][case.id] = dict(
                started=len(selected), passed=sum(row['passed'] for row in selected),
                failed_checks=dict(Counter(key for row in selected for key, ok in row.get('checks', {}).items() if not ok)),
                errors=dict(Counter(row['error'] for row in selected if row.get('error'))))
    return dict(latency=latency, controls=controls)


async def run_session(output_dir: Path, *, session_id, rounds=10, controls=1, interval=1.0,
                      settings=None, sleep=asyncio.sleep):
    fixture = load_fixture()
    if settings is None:
        settings = AISettings()
        settings.require_api()
    by_id = {case.id: case for case in fixture.cases}
    controls_by_id = {case.id: case for case in CONTROLS}
    plan = schedule(rounds, controls)
    report = dict(
        report_version=1, session_id=session_id, status='running', started_at=now(),
        purpose='#269 실행 문맥 위치 v7/v8 번갈아 비교', variants=dict(
            v7='v7 메시지 순서: 지시문 + 실행 문맥을 첫 시스템 메시지 하나로',
            v8='v8 메시지 순서: 지시문만 첫 시스템 메시지, 실행 문맥은 맨 끝 시스템 메시지'),
        scope='지시문·Tool 스키마·모델 설정은 같고 메시지 순서만 다르다',
        fixture_sha256=hashlib.sha256(DEFAULT_FIXTURE.read_bytes()).hexdigest(),
        prompt_sha256=hashlib.sha256(nodes.PROMPT.encode()).hexdigest(),
        persona_prompt_sha256=hashlib.sha256(nodes.PERSONA_PROMPT.encode()).hexdigest(),
        prompt_version=nodes.PROMPT_VERSION,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        profile=dict(rounds=rounds, controls=controls, interval_seconds=interval, concurrency=1,
                     case_ids=CASE_IDS, control_ids=[case.id for case in CONTROLS]),
        environment=execution_metadata('real_model', settings),
        planned=len(plan), finished=0,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    write_manifest(output_dir, report)
    rows = []
    try:
        with install_observers(), (output_dir / 'attempts.jsonl').open('x') as stream:
            for index, (phase, number, kind, case_id, variant) in enumerate(plan):
                attempt_id = f'{session_id}-{phase}-{number:03d}-{case_id}-{variant}'
                identity = dict(attempt_id=attempt_id, phase=phase, round=number, kind=kind,
                                case_id=case_id, variant=variant)
                if kind == 'latency':
                    request = make_request(fixture, by_id[case_id], attempt_id)
                else:
                    request = case_request(fixture, controls_by_id[case_id], attempt_id)
                request_data = request.model_dump(mode='json')
                append_event(stream, dict(event='started', started_at=now(), **identity, request=request_data,
                                          request_sha256=hashlib.sha256(json_text(request_data).encode()).hexdigest()))
                # 이 요청 동안만 메시지 순서를 바꾼다. 끝나면 현재 코드로 돌아간다.
                with patch.object(nodes, 'agent_messages', LAYOUTS[variant]):
                    if kind == 'latency':
                        measured, interrupted = await measure_attempt(by_id[case_id], request, chat_planning)
                        if interrupted:
                            raise asyncio.CancelledError
                    else:
                        measured = await measure_control(controls_by_id[case_id], request)
                row = dict(event='finished', finished_at=now(), **identity, **measured)
                append_event(stream, row)
                rows.append(row)
                report['finished'] = len(rows)
                write_manifest(output_dir, report)
                print(json.dumps(dict(**identity, outcome=row.get('outcome'), passed=row.get('passed'),
                                      seconds=round(row['ai_request_ms'] / 1000, 2)), ensure_ascii=False), flush=True)
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
        report.update(finished_at=now(), summary=summarize(rows))
        write_manifest(output_dir, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--controls', type=int, default=1)
    parser.add_argument('--interval-seconds', type=float, default=1.0)
    args = parser.parse_args()
    if args.rounds < 1 or args.controls < 0:
        parser.error('rounds는 1 이상, controls는 0 이상이어야 합니다')
    try:
        report = asyncio.run(run_session(args.output_dir, session_id=args.session_id, rounds=args.rounds,
                                         controls=args.controls, interval=args.interval_seconds))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print('측정을 중단했습니다. 기록과 세션 상태를 확인해 주세요.')
        return 130
    except Exception as error:
        # 예외 원문이나 공급자 응답을 콘솔에 노출하지 않는다.
        print(f'측정 실행 실패: {type(error).__name__}')
        return 1
    print(json.dumps(dict(status=report['status'], finished=report['finished']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
