"""#205: 같은 상태에서 기존/수정 지침의 보류 대상 해석을 번갈아 확인한다."""

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from app.ai import PlanningChatRequest, PlanningPublicResult, chat_planning, parse_resume_state
from app.ai.config import get_settings
from app.ai.features.planning.agent import nodes
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, now, write_manifest
from app.ai.scripts.planning_latency_inputs import AI_DIR, load_fixture, make_request
from app.ai.scripts.planning_latency_observation import capture_request, error_category, install_observers


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    expected_topics: tuple[str, ...] = ()
    initial_topics: tuple[str, ...] = ()
    previous_reply: str | None = None


CASES = (
    Case('generation_only', '예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마.'),
    Case('paraphrase', '인원은 60명으로 하자. 초안 생성은 나중에 하고 지금은 대화만 하자.'),
    Case('date_defer', '날짜는 나중에 정할게. 인원은 60명으로 바꿔줘. 초안은 만들지 마.', ('dates',)),
    Case('multiple_defer', '날짜와 장소는 나중에 정할게. 인원은 60명으로 바꿔줘. 초안은 만들지 마.',
         ('dates', 'location')),
    Case('context_defer', '그건 나중에 정할게. 인원은 60명으로 바꿔줘. 계획 초안은 만들지 마.',
         ('dates',), previous_reply='초안은 아직 만들지 않았어요. 행사 날짜는 언제로 정할까요?'),
    Case('date_resume', '날짜는 다시 얘기하자. 인원은 60명으로 바꿔줘. 초안은 만들지 마.',
         initial_topics=('dates',)),
)


def case_request(fixture, case, attempt_id):
    """이전 반복의 반환값을 재사용하지 않는다. 문맥/보류 초기값만 사례에 맞춰 바꾼다."""
    original = make_request(fixture, next(c for c in fixture.cases if c.id == 'C2'), attempt_id)
    data = original.model_dump(mode='json')
    draft = data['draft']
    draft['deferred_topics'] = list(case.initial_topics)
    payload = data['resume_state']['payload']
    payload['basis_draft'] = draft
    payload['generation']['offer']['basis_draft'] = draft
    # 저장 이력의 권유 결과도 같은 초기 조건을 가리키게 한다.
    for message in payload['history']:
        if message['role'] == 'tool' and message['name'] == 'update_generation_offer':
            result = json.loads(message['content'])
            result['offer']['basis_draft'] = draft
            message['content'] = json.dumps(result, ensure_ascii=False)
    if case.previous_reply:
        payload['history'][-1]['content'] = case.previous_reply
    data['message']['content'] = case.text
    return PlanningChatRequest.model_validate(data)


def inspect_boundary(request, result, case):
    """상태 변경 대상을 검사한다. 잠정/명시 차이는 점수 대신 진단값으로 남긴다."""
    view, state = result.view, result.next_state
    expected = request.draft.conditions.model_dump()
    expected['headcount'] = 60
    previous = request.resume_state.payload.history
    checks = dict(
        conditions_match=view.draft.conditions.model_dump() == expected,
        topics_match=set(view.draft.deferred_topics) == set(case.expected_topics),
        no_generation=view.generation_result is None and state.payload.generation.preview is None,
        generation_deferred=state.payload.generation.offer is not None
            and state.payload.generation.offer.status == 'deferred',
        other_metadata_preserved={k: v for k, v in view.draft.condition_meta.items() if k != 'headcount'}
            == {k: v for k, v in request.draft.condition_meta.items() if k != 'headcount'},
        history_preserved=state.payload.history[:len(previous)] == previous,
        json_roundtrip=parse_resume_state(state.model_dump_json()) == state,
        view_matches_state=view.draft == state.payload.basis_draft,
        request_matches=result.request_id == request.request_id and result.base_revision == request.base_revision,
        reply_present=bool(view.reply),
    )
    meta = view.draft.condition_meta.get('headcount')
    return dict(checks=checks, passed=all(checks.values()),
        extra_topics=sorted(set(view.draft.deferred_topics) - set(case.expected_topics)),
        missing_topics=sorted(set(case.expected_topics) - set(view.draft.deferred_topics)),
        headcount_status=meta.status if meta else None)


def summarize(rows):
    groups = {}
    for variant in ('baseline', 'candidate'):
        groups[variant] = {}
        for case in CASES:
            selected = [r for r in rows if r['variant'] == variant and r['case_id'] == case.id]
            groups[variant][case.id] = dict(started=len(selected),
                passed=sum(r.get('passed', False) for r in selected),
                extra_topic_requests=sum(bool(r.get('extra_topics')) for r in selected),
                missing_topic_requests=sum(bool(r.get('missing_topics')) for r in selected),
                failures=dict(Counter(k for r in selected for k, v in r.get('checks', {}).items() if not v)),
                errors=dict(Counter(r['error'] for r in selected if r.get('error'))),
                headcount_status=dict(Counter(r.get('headcount_status') for r in selected)))
    return groups


async def run(directory, *, baseline_ref, repeats, controls):
    directory.mkdir(parents=True, exist_ok=False)
    fixture = load_fixture()
    settings = get_settings()
    settings.require_api()
    relative = 'be/app/ai/features/planning/agent/prompts/chat.md'
    baseline = subprocess.check_output(['git', 'show', f'{baseline_ref}:{relative}'], text=True)
    candidate = nodes.PROMPT
    prompts = dict(baseline=baseline, candidate=candidate)
    for variant, prompt in prompts.items():
        (directory / f'{variant}-prompt.md').write_text(prompt)
    report = dict(status='running', started_at=now(), baseline_ref=baseline_ref,
        environment=execution_metadata('real_model', settings), repeats=repeats, controls=controls,
        cases=[asdict(c) for c in CASES], fixture_sha256=hashlib.sha256(
            (AI_DIR / 'tests/fixtures/eval/planning_latency.json').read_bytes()).hexdigest(),
        prompt_sha256={k: hashlib.sha256(v.encode()).hexdigest() for k, v in prompts.items()},
        scope='only system prompt differs; model/tool schema/runtime identical; no generation expected',
        evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        request_timeout_seconds=120, interval_seconds=0.5,
        planned=(repeats + controls * (len(CASES)-1))*2, finished=0)
    write_manifest(directory, report)
    rows = []
    try:
        with install_observers(), (directory / 'attempts.jsonl').open('x') as stream:
            for number in range(1, repeats+1):
                cases = list(CASES if number <= controls else CASES[:1])
                if number % 2 == 0:
                    cases.reverse()
                for case in cases:
                    variants = ('baseline', 'candidate') if number % 2 else ('candidate', 'baseline')
                    for variant in variants:
                        attempt_id = f'deferral-{variant}-{number:03d}-{case.id}'
                        request = case_request(fixture, case, attempt_id)
                        before = request.model_dump_json()
                        identity = dict(attempt_id=attempt_id, variant=variant, case_id=case.id, round=number)
                        append_event(stream, dict(event='started', **identity, started_at=now(), request=json.loads(before)))
                        row = dict(event='finished', **identity, passed=False)
                        # 한 요청씩 실행하고 지침만 교체한다. 실행 후 기존 지침으로 복원된다.
                        with patch.object(nodes, 'PROMPT', prompts[variant]), capture_request(time.perf_counter_ns) as trace:
                            start = time.perf_counter_ns()
                            trace.origin_ns = start
                            try:
                                result = await asyncio.wait_for(chat_planning(request), timeout=120)
                            except Exception as error:
                                row['error'] = error_category(error)
                            finally:
                                elapsed = (time.perf_counter_ns()-start)/1_000_000
                        row.update(ai_request_ms=elapsed, observation=trace.snapshot(elapsed), finished_at=now())
                        if 'error' not in row:
                            result = PlanningPublicResult.model_validate_json(result.model_dump_json())
                            row.update(inspect_boundary(request, result, case), result=result.model_dump(mode='json'))
                        if 'checks' in row:
                            row['checks']['request_unchanged'] = request.model_dump_json() == before
                            row['passed'] = all(row['checks'].values())
                        append_event(stream, row)
                        rows.append(row)
                        report['finished'] = len(rows)
                        write_manifest(directory, report)
                        print(json.dumps(dict(**identity, passed=row['passed'], extra=row.get('extra_topics'),
                                              error=row.get('error')), ensure_ascii=False), flush=True)
                        await asyncio.sleep(0.5)
        report['status'] = 'completed'
    except (asyncio.CancelledError, KeyboardInterrupt):
        report['status'] = 'interrupted'
        raise
    except Exception:
        report['status'] = 'runner_failed'
        raise
    finally:
        report.update(finished_at=now(), groups=summarize(rows))
        write_manifest(directory, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--baseline-ref', default='a60e8184c3ed17a9d688c4b2b040fb01307c4bce')
    parser.add_argument('--repeats', type=int, default=30)
    parser.add_argument('--controls', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.controls <= args.repeats:
        parser.error('1 <= controls <= repeats가 필요합니다')
    report = asyncio.run(run(args.output_dir, baseline_ref=args.baseline_ref,
                             repeats=args.repeats, controls=args.controls))
    print(json.dumps(report['groups'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
