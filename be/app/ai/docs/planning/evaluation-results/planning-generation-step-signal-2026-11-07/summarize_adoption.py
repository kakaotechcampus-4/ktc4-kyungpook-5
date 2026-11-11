"""measure_adoption.py 결과를 사례·경로별로 묶고, 측정 전에 정한 채택 기준을 판정한다. 모델 호출 없음.

be/에서 실행: .venv/bin/python -I <이 파일> <adoption-report.json>

기준(#389 코멘트, 측정 전에 정함):
1. 전체 시간: 사례마다 전체 p50(새 − 기존)이 +500ms 이내
2. 계획 검증 통과 수: 사례마다 기존 경로보다 1건까지 적은 것은 허용, 2건 이상 적으면 미달
3. 신호 순서: 새 경로의 생성 성공 요청마다 단계 신호 코드 순서 == 최종 초안 steps 코드 순서, 단계마다 정확히 한 번
4. 제외 단계: excluded_steps의 코드로 나간 신호가 없다
5. 기존 신호: generation_started → generation_writing → (단계 신호들) → generation_finished
"""
import json
import statistics
import sys
from pathlib import Path


def quantile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def total(attempt):
    return next(e['ms'] for e in attempt['events'] if e['kind'] == 'end')


def progress(attempt):
    return [e for e in attempt['events'] if e['kind'] == 'progress' and e['progress_kind'].startswith('generation_')]


def ok(attempt):
    return attempt['error'] is None and attempt['generation_status'] == 'generated'


def step_checks(attempt):
    events = progress(attempt)
    kinds = [e['progress_kind'] for e in events]
    steps = [e['step'] for e in events if e['progress_kind'] == 'generation_step']
    n = len(steps)
    order = kinds == ['generation_started', 'generation_writing', *['generation_step'] * n, 'generation_finished']
    same = [s['code'] for s in steps] == attempt['preview_codes'] and [s['index'] for s in steps] == list(range(n))
    excluded = not set(s['code'] for s in steps) & set(attempt['excluded_codes'] or ())
    return dict(signals=n, order=order, same=same, excluded=excluded)


def main(path: Path):
    report = json.loads(path.read_text())
    measured = [a for a in report['attempts'] if a['phase'] == 'measurement']
    print(f"model={report['model']} commit={report['commit'][:7]} dirty={report['product_code_dirty']} rounds={report['rounds']}")
    verdicts = []
    for case in ('G2', 'G1'):
        rows = {p: [a for a in measured if a['case'] == case and a['path'] == p] for p in ('before', 'after')}
        p50 = {p: statistics.median(total(a) for a in rows[p]) for p in rows}
        passed = {p: sum(ok(a) for a in rows[p]) for p in rows}
        for p in ('before', 'after'):
            times = [total(a) for a in rows[p]]
            signals = [sum(e['progress_kind'] == 'generation_step' for e in progress(a)) for a in rows[p]]
            print(f"{case} {p:<6} 생성 성공 {passed[p]}/{len(rows[p])}  전체 p50 {p50[p]:,.0f}  p95 {quantile(times, 0.95):,.0f}  "
                  f"단계 신호 수 {signals}")
        checks = [step_checks(a) for a in rows['after'] if ok(a)]
        before_signals = sum(sum(e['progress_kind'] == 'generation_step' for e in progress(a)) for a in rows['before'])
        by_round = {p: {a['round']: total(a) for a in rows[p]} for p in rows}
        diffs = [by_round['after'][r] - by_round['before'][r] for r in by_round['before'] if r in by_round['after']]
        diff = p50['after'] - p50['before']
        results = [
            ('1 전체 p50 차이', f"{diff:+,.0f}ms (짝 차이 중앙값 {statistics.median(diffs):+,.0f}ms, 새 경로가 빠른 짝 {sum(d < 0 for d in diffs)}/{len(diffs)})", diff <= 500),
            ('2 검증 통과 수', f"기존 {passed['before']} → 새 {passed['after']}", passed['after'] >= passed['before'] - 1),
            ('3 신호 = 최종 steps', f"{sum(c['same'] for c in checks)}/{len(checks)}", all(c['same'] for c in checks)),
            ('4 제외 단계 신호 없음', f"{sum(c['excluded'] for c in checks)}/{len(checks)}", all(c['excluded'] for c in checks)),
            ('5 신호 순서', f"{sum(c['order'] for c in checks)}/{len(checks)}, 기존 경로 단계 신호 {before_signals}개", all(c['order'] for c in checks) and before_signals == 0),
        ]
        for name, value, good in results:
            print(f"  {case} {name:<14} {value}  → {'통과' if good else '미달'}")
            verdicts.append(good)
    print('\n채택' if all(verdicts) else '\n미달 항목 있음')


main(Path(sys.argv[1]))
