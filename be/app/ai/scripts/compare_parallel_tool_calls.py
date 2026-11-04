"""#265: 대화 모델이 한 응답에 Tool을 하나만(single) / 여러 개(multi) 담게 한 설정을 같은 실행 안에서 번갈아 잰다.

지시문, Tool 스키마, 모델 설정, tools_node는 같고 `nodes.PARALLEL_TOOL_CALLS`만 다르다. 한 세션의 순서는 아래와 같다.
  준비 실행   C2를 single·multi로 한 번씩(집계 제외)
  본측정     라운드마다 single·multi 순서를 뒤집어 C2를 잰다
  대조 사례   #205의 보류 경계 사례를 single·multi로 --controls회씩(보류·조건 품질 확인용)
대조 사례 하나만 더 잴 때는 --rounds 0 --no-warmup --control-ids date_resume --controls 10처럼 쓴다.
본측정의 성공 판정·구간 시간·토큰 기록은 #263 측정기(measure_attempt)를, 대조 사례는 #205 검사기를 그대로 쓴다.
요청마다 이번 턴의 응답별 Tool 이름(`tool_batches`)을 함께 남겨 두 Tool을 한 응답에 담았는지 본다.
대조 사례는 응답별 Tool 인자·실행 결과(`tool_trace`), 최종 답변, 날짜 주제 처리(`dates_handling`)도 남긴다(#274).

  .venv/bin/python -m app.ai.scripts.compare_parallel_tool_calls --output-dir <작업 트리 밖 폴더> --session-id s1
"""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from app.ai import chat_planning
from app.ai.config import AISettings
from app.ai.features.planning.agent import nodes
from app.ai.scripts.compare_agent_context_layout import CONTROLS, measure_control
from app.ai.scripts.check_planning_deferrals import case_request
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, measure_attempt, now, write_manifest
from app.ai.scripts.planning_latency_inputs import DEFAULT_FIXTURE, json_text, load_fixture, make_request
from app.ai.scripts.planning_latency_observation import install_observers
from app.ai.scripts.planning_latency_summary import summarize_group

CASE_ID = 'C2'  # 조건 변경 + 생성 보류. 두 Tool을 한 응답에 담을 수 있는 대표 사례다.
VARIANTS = ('single', 'multi')
SETTINGS = dict(single=False, multi=True)


def schedule(rounds, controls, *, warmup=True, control_ids=None):
    """(phase, round, kind, case_id, variant) 목록. 순서 효과를 줄이려고 라운드마다 변형 순서를 뒤집는다."""
    chosen = [case for case in CONTROLS if control_ids is None or case.id in control_ids]
    plan = [('warmup', 0, 'latency', CASE_ID, variant) for variant in VARIANTS] if warmup else []
    for number in range(1, rounds + 1):
        variants = VARIANTS if number % 2 else tuple(reversed(VARIANTS))
        plan += [('measurement', number, 'latency', CASE_ID, variant) for variant in variants]
    for number in range(1, controls + 1):
        variants = VARIANTS if number % 2 else tuple(reversed(VARIANTS))
        plan += [('control', number, 'boundary', case.id, variant) for case in chosen for variant in variants]
    return plan


def turn_tools(request_data, result):
    """이번 턴에 대화 모델이 낸 응답별 Tool 이름과 마지막 생성 권유 상태.

    예: [["update_event_conditions", "update_generation_offer"]] → 한 응답에 두 Tool을 담았다.
        [["update_event_conditions"], ["update_generation_offer"]] → 응답 두 번에 나눠 담았다.
    """
    if not result:
        return dict(tool_batches=None, offer=None)
    before = len(request_data['resume_state']['payload']['history'])
    added = result['next_state']['payload']['history'][before:]
    batches = [[call['name'] for call in message['tool_calls']] for message in added if message.get('tool_calls')]
    payload = result['next_state']['payload']
    offer = payload['generation'].get('offer')
    return dict(tool_batches=batches, offer=None if offer is None else dict(
        status=offer['status'], basis_matches_draft=offer['basis_draft'] == payload['basis_draft']))


def tool_trace(request_data, result):
    """이번 턴의 응답별 Tool 요청(이름·인자)과 그 실행 결과, 토리의 최종 답변(#274).

    응답 하나가 목록 하나다. 예:
      [[{name: update_event_conditions, args: {changes: [...], resume_topics: [...]}, status: applied}],
       [{name: update_generation_offer, args: {action: defer, ...}, status: applied}]]
    실행 결과는 Tool 메시지를 tool_call_id로 짝지어 붙인다. 짝이 없으면 status는 None이다.
    """
    if not result:
        return dict(tool_trace=None, reply=None)
    before = len(request_data['resume_state']['payload']['history'])
    added = result['next_state']['payload']['history'][before:]
    outcomes = {}
    for message in added:
        if message['role'] != 'tool':
            continue
        try:
            content = json.loads(message['content'])
        except (TypeError, json.JSONDecodeError):
            content = {}
        outcomes[message['tool_call_id']] = dict(status=content.get('status'), reason=content.get('reason'))
    trace = [[dict(name=call['name'], args=call['args'],
                   **outcomes.get(call['id'], dict(status=None, reason=None)))
              for call in message['tool_calls']]
             for message in added if message.get('tool_calls')]
    return dict(tool_trace=trace, reply=result['view']['reply'])


def topic_handling(trace, topic='dates'):
    """조건 변경 Tool이 이번 턴에 한 주제를 어떻게 다뤘는지 한 단어로 나눈다(#274).

    resumed          resume_topics에 넣었고 적용됐다
    resume_rejected  resume_topics에 넣었지만 그 요청이 거절됐다 (재시도에서 다시 넣었으면 resumed)
    deferred         defer_topics에 넣었다 ("다시 얘기하자"를 "나중에"로 읽은 경우)
    omitted          조건 변경 Tool을 불렀지만 이 주제를 resume/defer 어디에도 넣지 않았다
    no_condition_call 조건 변경 Tool을 부르지 않았다
    """
    if trace is None:
        return None
    calls = [call for batch in trace for call in batch if call['name'] == nodes.TOOL_NAME]
    if not calls:
        return 'no_condition_call'
    def mentions(call, key):
        return any(item.get('topic') == topic for item in call['args'].get(key) or [])
    if any(mentions(call, 'resume_topics') and call['status'] != 'rejected' for call in calls):
        return 'resumed'
    if any(mentions(call, 'resume_topics') for call in calls):
        return 'resume_rejected'
    if any(mentions(call, 'defer_topics') for call in calls):
        return 'deferred'
    return 'omitted'


def summarize(rows):
    """변형별 집계. 본측정은 #263 집계(summarize_group)에 Tool 묶음 비율을, 대조 사례는 통과 수를 더한다."""
    latency, controls = {}, {}
    for variant in VARIANTS:
        selected = [row for row in rows if row['phase'] == 'measurement' and row['variant'] == variant]
        batches = [row['tool_batches'] for row in selected if row.get('tool_batches') is not None]
        latency[variant] = dict(
            summarize_group(selected, selected, selected),
            tool_batches=dict(
                requests=len(batches),
                bundled=sum(any(len(batch) > 1 for batch in item) for item in batches),
                patterns=dict(Counter(' | '.join('+'.join(batch) for batch in item) for item in batches))),
            offers=dict(Counter(json.dumps(row.get('offer'), sort_keys=True) for row in selected)))
        controls[variant] = {}
        for case in CONTROLS:
            chosen = [row for row in rows if row['phase'] == 'control'
                      and row['variant'] == variant and row['case_id'] == case.id]
            controls[variant][case.id] = dict(
                started=len(chosen), passed=sum(row['passed'] for row in chosen),
                failed_checks=dict(Counter(key for row in chosen for key, ok in row.get('checks', {}).items() if not ok)),
                errors=dict(Counter(row['error'] for row in chosen if row.get('error'))),
                # 통과/실패별로 날짜 주제를 어떻게 다뤘는지. 실패가 빠뜨림인지 다른 해석인지 여기서 본다(#274).
                dates_handling={outcome: dict(Counter(row['dates_handling'] for row in chosen
                                                      if row['passed'] == (outcome == 'passed')
                                                      and 'dates_handling' in row))
                                for outcome in ('passed', 'failed')})
    return dict(latency=latency, controls=controls)


async def run_session(output_dir: Path, *, session_id, rounds=10, controls=1, interval=1.0,
                      warmup=True, control_ids=None, settings=None, sleep=asyncio.sleep):
    fixture = load_fixture()
    if settings is None:
        settings = AISettings()
        settings.require_api()
    case = next(item for item in fixture.cases if item.id == CASE_ID)
    controls_by_id = {item.id: item for item in CONTROLS}
    plan = schedule(rounds, controls, warmup=warmup, control_ids=control_ids)
    report = dict(
        report_version=1, session_id=session_id, status='running', started_at=now(),
        purpose='#265 한 응답의 Tool 개수 single/multi 번갈아 비교', variants=dict(
            single='parallel_tool_calls=False: 한 응답에 Tool 하나',
            multi='parallel_tool_calls=True: 한 응답에 Tool 여러 개, tools_node가 차례로 실행'),
        scope='지시문·Tool 스키마·모델 설정·tools_node는 같고 parallel_tool_calls만 다르다',
        prompt_version=nodes.PROMPT_VERSION,
        fixture_sha256=hashlib.sha256(DEFAULT_FIXTURE.read_bytes()).hexdigest(),
        prompt_sha256=hashlib.sha256(nodes.PROMPT.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        profile=dict(rounds=rounds, controls=controls, interval_seconds=interval, concurrency=1, warmup=warmup,
                     case_ids=[CASE_ID], control_ids=sorted({item[3] for item in plan if item[0] == 'control'})),
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
                    request = make_request(fixture, case, attempt_id)
                else:
                    request = case_request(fixture, controls_by_id[case_id], attempt_id)
                request_data = request.model_dump(mode='json')
                append_event(stream, dict(event='started', started_at=now(), **identity, request=request_data,
                                          request_sha256=hashlib.sha256(json_text(request_data).encode()).hexdigest()))
                # 이 요청 동안만 설정을 바꾼다. 끝나면 현재 코드의 값으로 돌아간다.
                with patch.object(nodes, 'PARALLEL_TOOL_CALLS', SETTINGS[variant]):
                    if kind == 'latency':
                        measured, interrupted = await measure_attempt(case, request, chat_planning)
                        if interrupted:
                            raise asyncio.CancelledError
                        measured.update(turn_tools(request_data, measured.get('result')))
                    else:
                        measured = await measure_control(controls_by_id[case_id], request, keep_result=True)
                        # 통과/실패만으로는 원인을 못 본다. 응답별 Tool 인자와 날짜 주제 처리를 남긴다(#274).
                        measured.update(tool_trace(request_data, measured.get('result')))
                        measured['dates_handling'] = topic_handling(measured['tool_trace'])
                row = dict(event='finished', finished_at=now(), **identity, **measured)
                append_event(stream, row)
                rows.append(row)
                report['finished'] = len(rows)
                write_manifest(output_dir, report)
                print(json.dumps(dict(**identity, outcome=row.get('outcome'), passed=row.get('passed'),
                                      tools=row.get('tool_batches'), dates=row.get('dates_handling'),
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
    parser.add_argument('--no-warmup', action='store_true')
    parser.add_argument('--control-ids', nargs='+', choices=[case.id for case in CONTROLS])
    args = parser.parse_args()
    if args.rounds < 0 or args.controls < 0 or args.rounds + args.controls == 0:
        parser.error('rounds와 controls는 0 이상이고, 둘 중 하나는 1 이상이어야 합니다')
    try:
        report = asyncio.run(run_session(args.output_dir, session_id=args.session_id, rounds=args.rounds,
                                         controls=args.controls, interval=args.interval_seconds,
                                         warmup=not args.no_warmup, control_ids=args.control_ids))
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
