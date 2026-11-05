"""#266: 행사 계획 JSON 경로와 SSE 경로의 첫 반응 시간을 제품 HTTP로 번갈아 잰다.

    "예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마."
      JSON  POST /plan/chat         → 응답이 다 와야 화면이 바뀐다      (첫 반응 = 전체 시간)
      SSE   POST /plan/chat/stream  → progress · reply_delta · done   (첫 반응 = 첫 이벤트)

매 요청마다 새 행사를 만들고, 그 행사의 대화에 AI 측정기(#196)의 고정 시작 상태
(MT, 50명, 참가비 25,000원, 생성 권유 대기)를 넣는다. 그래서 앞 요청의 결과가 다음
요청의 입력이 되지 않는다. 시각은 이 스크립트가 받은 시각이라 브라우저 그리기 시간은 빠진다.

실행 (be/에서, BE 서버를 따로 켠 뒤. 실제 모델을 부르므로 요청마다 비용이 든다):

    DATABASE_URL=postgresql+psycopg://… .venv/bin/python scripts/measure_plan_stream_latency.py run \\
        --api http://localhost:8000/api/v1 --email … --password … --out /저장소/밖/session-1
    .venv/bin/python scripts/measure_plan_stream_latency.py summarize /저장소/밖/session-1

DATABASE_URL은 BE 서버와 같은 DB여야 한다(시작 상태를 직접 넣는다).
"""

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

import app.models  # noqa: F401  관계 설정을 위해 모델을 모두 불러온다.
from app.db.base import new_id
from app.db.session import get_engine, get_sessionmaker
from app.models.auth import Account
from app.models.chat import Conversation
from app.models.clubs import Member

BE_DIR = Path(__file__).resolve().parents[1]
FIXTURE = BE_DIR / 'app/ai/tests/fixtures/eval/planning_latency.json'
CASES = ('C2', 'G2')
MODES = ('json', 'sse')
# 채택 기준(측정 전에 #266에 적음): SSE 전체 시간 p50이 JSON보다 0.5초 넘게 늘지 않는다.
ALLOWED_TOTAL_INCREASE_MS = 500


def now() -> str:
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()


def schedule(rounds: int, warmup: bool) -> list[tuple[str, int, str, str]]:
    """(phase, round, case, mode). 사례 순서와 경로 순서를 라운드마다 뒤집어 순서 효과를 줄인다."""
    plan = [('warmup', 0, case, mode) for case in CASES for mode in MODES] if warmup else []
    for number in range(1, rounds + 1):
        cases = CASES if number % 2 else tuple(reversed(CASES))
        modes = MODES if number % 2 else tuple(reversed(MODES))
        plan.extend(('measurement', number, case, mode) for case in cases for mode in modes)
    return plan


async def find_member(email: str, club_id: str | None) -> tuple[str, str]:
    async with get_sessionmaker()() as session:
        account = await session.scalar(select(Account).where(Account.email == email))
        if account is None:
            raise SystemExit(f'계정이 없습니다: {email}')
        query = select(Member).where(Member.account_id == account.id)
        if club_id:
            query = query.where(Member.club_id == club_id)
        member = (await session.scalars(query.order_by(Member.created_at))).first()
        if member is None:
            raise SystemExit('이 계정이 속한 동아리가 없습니다')
        return member.club_id, member.id


async def seed_conversation(fixture: dict, *, club_id: str, event_id: str, member_id: str) -> None:
    """새 행사에 고정 시작 상태의 대화를 넣는다. AI 측정기와 같은 resume_state를 쓰고 소속 ID만 바꾼다."""
    conversation_id = new_id('cnv')
    state = {**fixture['resume_state'], 'club_id': club_id, 'event_id': event_id,
             'conversation_id': conversation_id}
    async with get_sessionmaker()() as session:
        session.add(Conversation(id=conversation_id, member_id=member_id, event_id=event_id,
                                 base_revision=fixture['base_revision'], resume_state=state))
        await session.commit()


def parse_sse(buffer: str) -> tuple[list[tuple[str, str]], str]:
    """완성된 이벤트만 꺼낸다. 주석 줄(': heartbeat')은 ('comment', '')로 돌려준다."""
    events = []
    while '\n\n' in buffer:
        block, buffer = buffer.split('\n\n', 1)
        name, data, comment = 'message', [], False
        for line in block.split('\n'):
            if line.startswith(':'):
                comment = True
            elif line.startswith('event:'):
                name = line[6:].strip()
            elif line.startswith('data:'):
                data.append(line[5:].lstrip())
        events.append(('comment', '') if comment and not data else (name, '\n'.join(data)))
    return events, buffer


def ms(start: int, end: int | None) -> float | None:
    return None if end is None else (end - start) / 1_000_000


def send(client: httpx.Client, *, case: str, mode: str, event_id: str, fixture: dict,
         attempt_id: str) -> dict:
    message = next(item['message'] for item in fixture['cases'] if item['id'] == 'C2')
    if case == 'C2':
        path = f'/events/{event_id}/plan/chat'
        body = {'messageId': f'{attempt_id}-user', 'message': message,
                'baseRevision': fixture['base_revision']}
    else:
        # FE의 버튼 생성과 같은 본문(hooks.ts: useCurrentConditions false).
        path = f'/events/{event_id}/plan/generate'
        body = {'baseRevision': fixture['base_revision'], 'useCurrentConditions': False}
    if mode == 'sse':
        path += '/stream'
    headers = {'Idempotency-Key': attempt_id}

    marks: dict[str, int | None] = dict(headers=None, first_event=None, first_progress=None,
                                        first_reply_delta=None, end=None)
    counts = dict(progress=0, reply_delta=0, reply_reset=0, heartbeat=0)
    final, final_event, status = None, None, None
    start = time.perf_counter_ns()
    with client.stream('POST', path, json=body, headers=headers) as response:
        marks['headers'] = time.perf_counter_ns()
        status = response.status_code
        if mode == 'json' or status != 200:
            raw = response.read()
            marks['end'] = time.perf_counter_ns()
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            final_event = 'done' if status == 200 else 'http_error'
            final = (payload or {}).get('data') if status == 200 else (payload or {}).get('error')
        else:
            buffer = ''
            for chunk in response.iter_text():
                received = time.perf_counter_ns()
                events, buffer = parse_sse(buffer + chunk)
                for name, data in events:
                    if name == 'comment':
                        counts['heartbeat'] += 1
                        continue
                    if marks['first_event'] is None:
                        marks['first_event'] = received
                    if name == 'progress' and marks['first_progress'] is None:
                        marks['first_progress'] = received
                    if name == 'reply_delta' and marks['first_reply_delta'] is None:
                        marks['first_reply_delta'] = received
                    if name in counts:
                        counts[name] += 1
                    if name in {'done', 'error'}:
                        marks['end'] = received
                        final_event, final = name, json.loads(data)
            if marks['end'] is None:
                marks['end'] = time.perf_counter_ns()
                final_event = 'closed_without_done'

    total = ms(start, marks['end'])
    timing = dict(
        total_ms=total,
        headers_ms=ms(start, marks['headers']),
        # 화면이 처음 바뀌는 시각. JSON은 응답을 다 받아야 바뀐다.
        first_visible_ms=total if mode == 'json' else ms(start, marks['first_event']),
        first_progress_ms=ms(start, marks['first_progress']),
        first_reply_delta_ms=ms(start, marks['first_reply_delta']),
    )
    return dict(http_status=status, final_event=final_event, events=counts, **timing, view=final)


def check(case: str, view: dict | None, fixture: dict, steps: int | None) -> dict:
    """측정이 끝난 뒤 결과를 검사한다(시간에 넣지 않음). AI 측정기의 C2/G2 검사 중 HTTP로 보이는 것."""
    if not isinstance(view, dict) or 'draft' not in view:
        return dict(done=False)
    base = fixture['resume_state']['payload']['basis_draft']['conditions']
    conditions = view['draft']['conditions']
    expected = {key: base.get(key) for key in ('event_type', 'headcount', 'fee_per_person')}
    actual = dict(event_type=conditions.get('eventType'), headcount=conditions.get('headcount'),
                  fee_per_person=conditions.get('feePerPerson'))
    if case == 'C2':
        expected['headcount'] = 60
        meta = view['draft']['conditionMeta'].get('headcount') or {}
        return dict(done=True, conditions_match=actual == expected,
                    changed_fields_match=view['changedFields'] == ['headcount'],
                    headcount_specified=meta.get('status') == 'specified',
                    no_generation=view['generationResult'] is None, reply=bool(view['reply']))
    generation = view['generationResult'] or {}
    return dict(done=True, conditions_match=actual == expected,
                generated=generation.get('status') == 'generated',
                steps_saved=bool(steps), no_reply=view['reply'] is None)


def metadata(args) -> dict:
    def git(*command):
        return subprocess.check_output(['git', *command], text=True, cwd=BE_DIR).strip()
    return dict(
        started_at=now(), api=args.api, rounds=args.rounds, warmup=not args.no_warmup,
        interval_seconds=args.interval, fixture=str(FIXTURE.relative_to(BE_DIR)),
        commit=git('rev-parse', 'HEAD'), dirty=bool(git('status', '--porcelain')),
        # 서버가 쓰는 값과 같은지는 실행하는 사람이 같은 .env로 맞춘다. 주소·키는 남기지 않는다.
        model=os.environ.get('AI_MODEL'), python=platform.python_version(),
        platform=platform.platform(), httpx=httpx.__version__,
        allowed_total_increase_ms=ALLOWED_TOTAL_INCREASE_MS,
        measured_from='script receive time (perf_counter_ns); browser rendering not included',
    )


def run(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    fixture = json.loads(FIXTURE.read_text())
    # DB 엔진은 처음 쓴 이벤트 루프에 묶이므로 루프 하나를 끝까지 쓴다.
    loop = asyncio.new_event_loop()
    club_id, member_id = loop.run_until_complete(find_member(args.email, args.club_id))
    session_meta = metadata(args)
    (out / 'session.json').write_text(json.dumps(session_meta, ensure_ascii=False, indent=2) + '\n')

    with httpx.Client(base_url=args.api, timeout=httpx.Timeout(240.0)) as client:
        login = client.post('/auth/login', json={'email': args.email, 'password': args.password})
        login.raise_for_status()
        client.headers['Authorization'] = f"Bearer {login.json()['data']['accessToken']}"
        plan = schedule(args.rounds, not args.no_warmup)
        with (out / 'attempts.jsonl').open('x') as log:
            for index, (phase, number, case, mode) in enumerate(plan, 1):
                attempt_id = f'{args.session_id}-{phase}-{number:02d}-{case}-{mode}'
                created = client.post('/events', json={'clubId': club_id, 'title': attempt_id})
                created.raise_for_status()
                event_id = created.json()['data']['id']
                loop.run_until_complete(seed_conversation(fixture, club_id=club_id, event_id=event_id,
                                                          member_id=member_id))
                started_at = now()
                try:
                    row = send(client, case=case, mode=mode, event_id=event_id, fixture=fixture,
                               attempt_id=attempt_id)
                except httpx.HTTPError as error:
                    row = dict(http_status=None, final_event='transport_error',
                               error_type=type(error).__name__, view=None)
                steps = None
                if case == 'G2' and row.get('final_event') == 'done':
                    listed = client.get(f'/events/{event_id}/plan/steps')
                    steps = len(listed.json().get('data') or []) if listed.status_code == 200 else None
                view = row.pop('view')
                checks = check(case, view if row.get('final_event') == 'done' else None, fixture, steps)
                record = dict(attempt_id=attempt_id, phase=phase, round=number, case=case, mode=mode,
                              event_id=event_id, started_at=started_at, steps_saved=steps,
                              success=bool(checks) and all(checks.values()), checks=checks,
                              reply=(view or {}).get('reply') if isinstance(view, dict) else None,
                              failure=None if isinstance(view, dict) and 'draft' in view else view,
                              **row)
                log.write(json.dumps(record, ensure_ascii=False) + '\n')
                log.flush()
                shown = record.get('first_visible_ms')
                print(f"[{index}/{len(plan)}] {phase} r{number} {case} {mode:4} "
                      f"{record['final_event']} success={record['success']} "
                      f"first={shown and round(shown)}ms total={record.get('total_ms') and round(record['total_ms'])}ms",
                      flush=True)
                time.sleep(args.interval)
    loop.run_until_complete(get_engine().dispose())
    loop.close()
    session_meta['finished_at'] = now()
    (out / 'session.json').write_text(json.dumps(session_meta, ensure_ascii=False, indent=2) + '\n')


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # 최근접 순위(nearest-rank). 표본 10개의 p95는 가장 느린 값이다.
    rank = max(1, -(-int(q * 100) * len(ordered) // 100))
    return ordered[rank - 1]


def summarize(directory: Path) -> dict:
    rows = [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]
    measured = [row for row in rows if row['phase'] == 'measurement']
    groups = {}
    for case in CASES:
        for mode in MODES:
            group = [row for row in measured if row['case'] == case and row['mode'] == mode]
            ok = [row for row in group if row['success']]
            stats = dict(attempts=len(group), success=len(ok))
            for field in ('first_visible_ms', 'first_progress_ms', 'first_reply_delta_ms', 'total_ms'):
                values = [row[field] for row in ok if row.get(field) is not None]
                stats[field] = dict(n=len(values), p50=statistics.median(values) if values else None,
                                    p95=percentile(values, 0.95))
            groups[f'{case}/{mode}'] = stats
    comparisons = {}
    for case in CASES:
        json_stats, sse_stats = groups[f'{case}/json'], groups[f'{case}/sse']
        pairs = []
        for number in sorted({row['round'] for row in measured}):
            pair = {row['mode']: row for row in measured
                    if row['case'] == case and row['round'] == number and row['success']}
            if len(pair) == 2:
                pairs.append(pair)
        increase = (sse_stats['total_ms']['p50'] - json_stats['total_ms']['p50']
                    if sse_stats['total_ms']['p50'] is not None and json_stats['total_ms']['p50'] is not None
                    else None)
        comparisons[case] = dict(
            total_p50_increase_ms=increase,
            within_allowed=increase is not None and increase <= ALLOWED_TOTAL_INCREASE_MS,
            first_visible_p50_saved_ms=(json_stats['first_visible_ms']['p50'] - sse_stats['first_visible_ms']['p50']
                                        if sse_stats['first_visible_ms']['p50'] is not None
                                        and json_stats['first_visible_ms']['p50'] is not None else None),
            paired_rounds=len(pairs),
            sse_first_visible_earlier=sum(p['sse']['first_visible_ms'] < p['json']['first_visible_ms'] for p in pairs),
            sse_total_faster=sum(p['sse']['total_ms'] < p['json']['total_ms'] for p in pairs),
        )
    failures = [dict(attempt_id=row['attempt_id'], final_event=row['final_event'], checks=row['checks'],
                     failure=row.get('failure')) for row in rows if not row['success']]
    summary = dict(session=json.loads((directory / 'session.json').read_text()), groups=groups,
                   comparisons=comparisons, failures=failures)
    (directory / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


def print_summary(summary: dict) -> None:
    def sec(value):
        return '-' if value is None else f'{value / 1000:.2f}'
    print('사례/경로   성공   첫 반응 p50/p95   첫 진행 p50   답변 첫 글자 p50   전체 p50/p95 (초)')
    for key, stats in summary['groups'].items():
        print(f"{key:10} {stats['success']:>2}/{stats['attempts']:<2}  "
              f"{sec(stats['first_visible_ms']['p50']):>6} / {sec(stats['first_visible_ms']['p95']):<6}  "
              f"{sec(stats['first_progress_ms']['p50']):>8}      {sec(stats['first_reply_delta_ms']['p50']):>8}       "
              f"{sec(stats['total_ms']['p50']):>6} / {sec(stats['total_ms']['p95'])}")
    for case, result in summary['comparisons'].items():
        print(f"{case}: 전체 p50 증가 {sec(result['total_p50_increase_ms'])}초 "
              f"(기준 {ALLOWED_TOTAL_INCREASE_MS / 1000}초 이내: {result['within_allowed']}), "
              f"첫 반응 p50 {sec(result['first_visible_p50_saved_ms'])}초 앞당김, "
              f"짝 {result['paired_rounds']}개 중 첫 반응이 SSE가 빠름 {result['sse_first_visible_earlier']}, "
              f"전체가 SSE가 빠름 {result['sse_total_faster']}")
    if summary['failures']:
        print(f"실패 {len(summary['failures'])}건: " + ', '.join(f['attempt_id'] for f in summary['failures']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    run_parser = commands.add_parser('run')
    run_parser.add_argument('--api', default='http://localhost:8000/api/v1')
    run_parser.add_argument('--email', required=True)
    run_parser.add_argument('--password', required=True)
    run_parser.add_argument('--club-id')
    run_parser.add_argument('--out', required=True)
    run_parser.add_argument('--session-id', default=datetime.now().strftime('s%m%d%H%M'))
    run_parser.add_argument('--rounds', type=int, default=10)
    run_parser.add_argument('--interval', type=float, default=1.0)
    run_parser.add_argument('--no-warmup', action='store_true')
    summary_parser = commands.add_parser('summarize')
    summary_parser.add_argument('directory')
    args = parser.parse_args()
    if args.command == 'run':
        run(args)
        print_summary(summarize(Path(args.out)))
    else:
        print_summary(summarize(Path(args.directory)))


if __name__ == '__main__':
    main()
