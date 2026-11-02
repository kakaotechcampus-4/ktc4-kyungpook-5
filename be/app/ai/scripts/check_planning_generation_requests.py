"""#239: 같은 저장 상태의 채팅/버튼 생성 경로를 비교한다. 제품 동작은 바꾸지 않는다."""

import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.ai import (
    AIConfigError, PlanningChatRequest, PlanningConditions, PlanningDraft, PlanningPreviewRequest,
    PlanningPublicResult, chat_planning, generate_planning_preview, parse_resume_state,
)
from app.ai.config import AISettings
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph, nodes
from app.ai.features.planning.generation import graph as generation_graph
from app.ai.features.planning.generation.offers import same_basis
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, now, write_manifest
from app.ai.scripts.planning_latency_inputs import AI_DIR, request_hashes
from app.ai.scripts.planning_latency_observation import capture_request, error_category, install_observers


CASE_IDS = ('current_offer', 'changed_headcount', 'specified_dates')
ROUTES = ('chat', 'button')
DEFAULT_FIXTURE = AI_DIR / 'tests/fixtures/eval/planning_generation_requests.json'
DIRECT_REQUEST = '최신 조건으로 초안 만들어줘.'
CONTEXT = dict(club_id='synthetic-239-club', event_id='synthetic-239-event',
               conversation_id='synthetic-239-conversation', reference_date='2026-11-03',
               timezone='Asia/Seoul')


def tool(name, args, call_id):
    return dict(name=name, args=args, id=call_id)


def condition_change(field, value, text, message_id, status='specified'):
    return dict(op='SET', change=dict(field=field, value=value), status=status,
                evidence=dict(message_id=message_id, quote=text))


async def build_fixture():
    """실제 공개 경계/처리기로 합성 이력을 만든다. 모델과 생성기를 호출하지 않는다."""
    async def turn(text, message_id, calls, reply, previous=None):
        request = PlanningChatRequest(**CONTEXT, request_id=f'fixture-{message_id}',
            base_revision=0 if previous is None else 1, message=dict(id=message_id, content=text),
            draft=previous.view.draft if previous else PlanningDraft(),
            resume_state=previous.next_state if previous else None)
        answers = iter([AIMessage(content='', tool_calls=calls), AIMessage(content=reply)])

        async def agent(*args, **kwargs):
            return next(answers)

        async def unexpected_generation(*args, **kwargs):
            raise AssertionError('fixture 작성 중에는 생성하지 않습니다')

        with patch.object(agent_graph, 'call_agent_model', agent), \
             patch.object(public_workflow, 'run_plan_generation', unexpected_generation):
            result = await chat_planning(request)
        assert next(answers, None) is None
        return result

    text = ('워크숍이고 인원은 30명, 참가비는 30000원, 장소는 가평 펜션이야. '
            '일정은 일단 2026년 11월 7일 당일로 잡자. 이 조건으로 초안을 만들지 물어봐 줘.')
    values = dict(event_type='WORKSHOP', headcount=30, fee_per_person=30000,
                  location='가평 펜션', start_date='2026-11-07', end_date='2026-11-07')
    changes = [condition_change(k, v, text, 'fixture-initial',
                               'tentative' if k in ('start_date', 'end_date') else 'specified')
               for k, v in values.items()]
    initial = await turn(text, 'fixture-initial', [
        tool(nodes.TOOL_NAME, dict(changes=changes), 'fixture-set'),
        tool(nodes.OFFER_TOOL_NAME, dict(action='offer', reason='현재 워크숍 조건으로 준비 순서 초안을 제안해요.'),
             'fixture-offer')], '30명·참가비 30000원·가평 펜션·11월 7일 잠정 일정으로 초안을 만들까요?')
    text = '인원을 40명으로 바꿔줘.'
    headcount = await turn(text, 'fixture-headcount', [tool(nodes.TOOL_NAME,
        dict(changes=[condition_change('headcount', 40, text, 'fixture-headcount')]),
        'fixture-change-headcount')], '인원을 40명으로 바꿨어요. 다른 조건은 유지했어요.', initial)
    text = '일정은 같은 2026년 11월 7일 당일로 확정해줘.'
    dates = await turn(text, 'fixture-dates', [tool(nodes.TOOL_NAME, dict(changes=[
        condition_change(k, '2026-11-07', text, 'fixture-dates') for k in ('start_date', 'end_date')]),
        'fixture-specify-dates')], '일정은 11월 7일 당일로 명시했어요. 다른 조건은 유지했어요.', initial)
    fixture = dict(fixture_version=1, provenance='합성 워크숍. 공개 함수에 대화 응답만 주입해 작성. 멘토 이력 아님.',
                   actual_provider_calls=0, reference_date=CONTEXT['reference_date'], timezone=CONTEXT['timezone'],
                   direct_request=DIRECT_REQUEST,
                   cases=[dict(id=case_id, resume_state=result.next_state.model_dump(mode='json'))
                          for case_id, result in zip(CASE_IDS, (initial, headcount, dates), strict=True)])
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture):
    if (fixture.get('fixture_version') != 1 or fixture.get('actual_provider_calls') != 0
            or fixture.get('direct_request') != DIRECT_REQUEST
            or tuple(c['id'] for c in fixture.get('cases', ())) != CASE_IDS):
        raise ValueError('제공된 합성 세 상태와 명시적 직접 요청이 필요합니다')
    states = [parse_resume_state(json.dumps(c['resume_state'])) for c in fixture['cases']]
    initial = states[0].payload.basis_draft
    if initial.conditions != PlanningConditions(event_type='WORKSHOP', headcount=30, fee_per_person=30000,
            location='가평 펜션', start_date='2026-11-07', end_date='2026-11-07') or initial.deferred_topics:
        raise ValueError('고정한 합성 워크숍 조건이 필요합니다')
    for index, state in enumerate(states):
        payload = state.payload
        generation, draft = payload.generation, payload.basis_draft
        if (generation.offer is None or generation.offer.status != 'pending' or generation.preview is not None
                or generation.condition_change_pending or generation.pending_condition_fields
                or generation.offer != states[0].payload.generation.offer
                or public_workflow.planning_generation_readiness(draft, resume_state=state).can_generate is not True):
            raise ValueError('생성 전 유효 조건과 동일한 최초 권유가 필요합니다')
        if same_basis(generation.offer.basis_draft, draft) != (index == 0):
            raise ValueError('정상/오래된 권유의 기준이 맞지 않습니다')
    headcount, dates = (s.payload.basis_draft for s in states[1:])
    expected = initial.conditions.model_copy(update={'headcount': 40})
    if (headcount.conditions != expected or dates.conditions != initial.conditions
            or any(initial.condition_meta[k].status != 'tentative' or dates.condition_meta[k].status != 'specified'
                   for k in ('start_date', 'end_date'))):
        raise ValueError('인원 또는 일정의 잠정/명시 변화가 맞지 않습니다')
    return fixture


def make_request(fixture, case_id, route, attempt_id):
    case = next(c for c in fixture['cases'] if c['id'] == case_id)
    # 같은 JSON을 매번 새로 복원한다. 앞 요청의 preview나 변경 상태는 다음 실험에 넣지 않는다.
    state = parse_resume_state(json.dumps(case['resume_state']))
    common = dict(club_id=state.club_id, event_id=state.event_id, conversation_id=state.conversation_id,
                  reference_date=fixture['reference_date'], timezone=fixture['timezone'],
                  base_revision=1, request_id=attempt_id, draft=state.payload.basis_draft, resume_state=state)
    if route == 'button':
        return PlanningPreviewRequest(**common)
    if route != 'chat':
        raise ValueError('지원하지 않는 경로입니다')
    return PlanningChatRequest(**common, message=dict(id=f'{attempt_id}-user', content=fixture['direct_request']))


def schedule(rounds):
    if type(rounds) is not int or rounds < 1:
        raise ValueError('반복 횟수는 1 이상 정수여야 합니다')
    return [(number, case_id, route) for number in range(1, rounds + 1)
            for case_id in (CASE_IDS if number % 2 else tuple(reversed(CASE_IDS)))
            for route in (ROUTES if number % 2 else tuple(reversed(ROUTES)))]


@contextmanager
def capture_tools():
    """합성 입력의 Tool 인자/결과만 선별한다. 모델 응답 블록과 추론은 보관하지 않는다."""
    activity = dict(requests=[], results=[])
    original_agent, original_tools = agent_graph.call_agent_model, agent_graph.tools_node

    async def agent(*args, **kwargs):
        response = await original_agent(*args, **kwargs)
        if isinstance(response, AIMessage):
            activity['requests'].extend(deepcopy(response.tool_calls))
        return response

    async def tools(*args, **kwargs):
        update = await original_tools(*args, **kwargs)
        for message in update['messages']:
            data = json.loads(message.content)
            activity['results'].append(dict(call_id=message.tool_call_id, name=message.name,
                **{k: data[k] for k in ('status', 'reason', 'changed_fields', 'model_calls') if k in data}))
        return update

    with patch.object(agent_graph, 'call_agent_model', agent), patch.object(agent_graph, 'tools_node', tools):
        yield activity


def inspect_result(request, result, observation):
    view, state = result.view, result.next_state
    previous = request.resume_state
    generation = view.generation_result
    preview = generation.preview if generation else None
    generated = bool(generation and generation.status == 'generated')
    checks = dict(
        generated=generated,
        conditions_preserved=view.draft.conditions == request.draft.conditions,
        draft_preserved=view.draft == request.draft,
        history_preserved=state.payload.history[:len(previous.payload.history)] == previous.payload.history,
        view_matches_state=view.draft == state.payload.basis_draft,
        json_roundtrip=parse_resume_state(state.model_dump_json()) == state,
        request_identity=result.request_id == request.request_id and result.base_revision == request.base_revision,
        previous_preview_preserved=generated or state.payload.generation.preview == previous.payload.generation.preview,
        preview_consistent=not generated or (preview == state.payload.generation.preview
            and preview.basis_draft == request.draft and view.preview_is_current),
    )
    if isinstance(request, PlanningPreviewRequest):
        checks['button_no_agent'] = observation['model_call_attempts']['agent_model'] == 0
        checks['button_history_unchanged'] = state.payload.history == previous.payload.history
        checks['button_no_reply'] = view.reply is None
    if generated:
        source = 'chat' if isinstance(request, PlanningChatRequest) else 'button'
        trigger_id = request.message.id if source == 'chat' else request.request_id
        checks['preview_trigger'] = preview.trigger.source == source and preview.trigger.request_id == trigger_id
    return dict(checks=checks, generation_status=generation.status if generation else None,
                reply=view.reply, draft=view.draft.model_dump(mode='json'),
                generation_result=generation.model_dump(mode='json') if generation else None,
                history_count=len(state.payload.history))


async def attempt(request, *, timeout=180):
    before = request.model_dump_json()
    row = dict(outcome='failed', returned_normally=False)
    interrupted = False
    with capture_request(time.perf_counter_ns) as trace, capture_tools() as activity:
        started = time.perf_counter_ns()
        trace.origin_ns = started
        try:
            call = chat_planning if isinstance(request, PlanningChatRequest) else generate_planning_preview
            result = await asyncio.wait_for(call(request), timeout=timeout)
            row['returned_normally'] = True
        except (asyncio.CancelledError, KeyboardInterrupt):
            interrupted = True
            row.update(outcome='interrupted', error_type='CancelledError', failure_category='interrupted')
        except Exception as error:
            row.update(error_type=type(error).__name__,
                       failure_category='request_timeout' if isinstance(error, TimeoutError) else error_category(error))
            origin = trace.origin_for(error)
            if origin:
                row['failure_stage'] = origin['stage']
            if isinstance(error, AIConfigError):
                row['stop_session'] = 'configuration_error'
            elif getattr(error, 'status_code', None) == 400:
                row['stop_session'] = 'request_error'
        finally:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
    observation = trace.snapshot(elapsed)
    row.update(ai_request_ms=elapsed, observation=observation, tool_activity=activity,
               generation_entered=any(s['stage'] == 'generation' for s in observation['spans']))
    offer = request.resume_state.payload.generation.offer
    row['stale_offer_id_used'] = bool(offer and not same_basis(offer.basis_draft, request.draft) and any(
        c['name'] == nodes.GENERATE_TOOL_NAME and c['args'].get('offer_id') == offer.id
        for c in activity['requests']))
    if row['returned_normally']:
        try:
            parsed = PlanningPublicResult.model_validate_json(result.model_dump_json())
            row.update(inspect_result(request, parsed, observation))
            row['checks']['request_unchanged'] = request.model_dump_json() == before
            row['outcome'] = 'success' if all(row['checks'].values()) else 'failed'
            if row['outcome'] == 'failed':
                origin = trace.generation_failure()
                row['failure_category'] = (origin['failure_code'] if origin else
                                           'expectation_failed' if row['generation_entered'] else 'before_generation')
        except Exception as error:
            row.update(failure_category='invalid_result', error_type=type(error).__name__)
    return row, interrupted


def summarize(rows):
    groups = {}
    for case_id in CASE_IDS:
        groups[case_id] = {}
        for route in ROUTES:
            selected = [r for r in rows if r['case_id'] == case_id and r['route'] == route]
            groups[case_id][route] = dict(finished=len(selected),
                success=sum(r['outcome'] == 'success' for r in selected),
                entered=sum(r['generation_entered'] for r in selected),
                stale_offer_id_used=sum(r['stale_offer_id_used'] for r in selected),
                failures=dict(Counter(r.get('failure_category', 'unknown') for r in selected if r['outcome'] != 'success')),
                failed_checks=dict(Counter(k for r in selected for k, v in r.get('checks', {}).items() if not v)))
    return groups


async def run(directory, fixture_path=DEFAULT_FIXTURE, *, rounds=3):
    raw = fixture_path.read_bytes()
    fixture = validate_fixture(json.loads(raw))
    plan = schedule(rounds)
    settings = AISettings()
    settings.require_api()
    report = dict(report_version=1, status='running', started_at=now(), planned=len(plan), finished=0,
        rounds=rounds, environment=execution_metadata('real_model', settings),
        evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_sha256=hashlib.sha256(raw).hexdigest(),
        prompt_versions=dict(agent=nodes.PROMPT_VERSION, generation=generation_graph.PROMPT_VERSION),
        scope='합성 입력의 실제 모델 공개 AI 함수 비교. DB/HTTP/FE와 다른 모델은 미검증.',
        request_timeout_seconds=180, interval_seconds=0.5, concurrency=1,
        planned_attempts=[dict(round=n, case_id=c, route=r) for n, c, r in plan])
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'fixture.json').write_bytes(raw)
    write_manifest(directory, report)
    rows = []
    try:
        with install_observers(), (directory / 'attempts.jsonl').open('x') as stream:
            for number, case_id, route in plan:
                attempt_id = f'gen239-{number:02d}-{case_id}-{route}'
                request = make_request(fixture, case_id, route, attempt_id)
                identity = dict(attempt_id=attempt_id, round=number, case_id=case_id, route=route)
                append_event(stream, dict(event='started', started_at=now(), **identity,
                    **request_hashes(request), request=request.model_dump(mode='json')))
                row, interrupted = await attempt(request)
                row.update(identity)
                rows.append(row)
                append_event(stream, dict(event='finished', finished_at=now(), **row))
                report.update(finished=len(rows), summary=summarize(rows))
                write_manifest(directory, report)
                print(f'{attempt_id}: {row["outcome"]}, generation={row["generation_entered"]}, '
                      f'stale_id={row["stale_offer_id_used"]}', flush=True)
                if interrupted:
                    raise asyncio.CancelledError
                if row.get('stop_session'):
                    report['status'] = 'stopped_' + row['stop_session']
                    break
                await asyncio.sleep(0.5)
            else:
                report['status'] = 'completed'
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
    parser.add_argument('--fixture', type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument('--build-fixture', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.build_fixture:
            fixture = asyncio.run(build_fixture())
            with args.build_fixture.open('x') as stream:
                json.dump(fixture, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            return 0
        if args.dry_run:
            raw = args.fixture.read_bytes()
            validate_fixture(json.loads(raw))
            print(json.dumps(dict(fixture_sha256=hashlib.sha256(raw).hexdigest(), provider_calls=0,
                                  plan=schedule(args.rounds)), ensure_ascii=False, indent=2))
            return 0
        if args.output_dir is None:
            parser.error('--output-dir가 필요합니다')
        report = asyncio.run(run(args.output_dir, args.fixture, rounds=args.rounds))
        return 0 if report['status'] == 'completed' and all(
            group['success'] == args.rounds for routes in report['summary'].values() for group in routes.values()) else 1
    except (asyncio.CancelledError, KeyboardInterrupt):
        print('중단 상태와 이미 기록한 결과를 보존했습니다.')
        return 130
    except Exception as error:
        print(f'진단 실행 오류: {type(error).__name__}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
