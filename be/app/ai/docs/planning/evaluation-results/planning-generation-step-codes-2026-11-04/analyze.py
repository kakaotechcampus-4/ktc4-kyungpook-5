"""#276 결과 분석: 보존한 원본에서 채택 기준에 필요한 값만 다시 집계한다. 모델·API 설정을 쓰지 않는다.

  python3 app/ai/docs/planning/evaluation-results/planning-generation-step-codes-2026-11-04/analyze.py > /tmp/analysis.json

- step-codes/: 출력 형식 v1/v2 비교(③), reasoning-v2/: v2 위에서 추론 깊이 default/low 비교(④).
- 변형별 통과 수, 실패 분류, 검증 거절 규칙, 응답에 카탈로그 밖 코드가 있던 요청 수,
  성공 요청과 생성 호출 1번의 p50/p95(R7 선형 보간), 세션별 생성 호출 p50, 성공 초안 단계 수, 짝 비교.
"""
import json
from collections import Counter
from pathlib import Path
from statistics import median

HERE = Path(__file__).parent


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def seconds(value):
    return None if value is None else round(value / 1000, 2)


def generation_ms(row):
    return [span['duration_ms'] for span in row.get('observation', {}).get('spans', [])
            if span['stage'] == 'generation_model' and span.get('duration_ms') is not None]


def load(folders):
    rows, sessions = [], []
    for folder in folders:
        report = json.loads((folder / 'session.json').read_text())
        sessions.append(report)
        for line in (folder / 'attempts.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row['event'] == 'finished' and row['phase'] == 'measurement':
                rows.append(dict(row, session=report['session_id']))
    return rows, sessions


def variant_summary(selected):
    ok = [row for row in selected if row['outcome'] == 'success']
    outside = [row for row in selected if row.get('outside_catalog_codes')]
    calls = [ms for row in selected for ms in generation_ms(row)]
    steps = [row['output']['step_count'] for row in ok]
    return dict(
        n=len(selected), success=len(ok),
        failures=dict(Counter(row['failure']['category'] for row in selected if row.get('failure'))),
        violations=dict(Counter(item['rule'] for row in selected for item in row.get('violations', []))),
        # 응답에 카탈로그 밖 코드(CANCEL_* 등)가 있던 요청 수와 그 결과. #276 기준 ①
        outside_catalog_requests=len(outside),
        outside_catalog_outcomes=dict(Counter(row['failure']['category'] if row.get('failure') else row['outcome']
                                              for row in outside)),
        success_p50_s=seconds(median(row['ai_request_ms'] for row in ok)) if ok else None,
        success_p95_s=seconds(pct([row['ai_request_ms'] for row in ok], .95)),
        generation_call_p50_s=seconds(median(calls)) if calls else None,
        generation_call_p95_s=seconds(pct(calls, .95)),
        generation_call_p50_by_session={
            session: seconds(median(ms for row in selected if row['session'] == session for ms in generation_ms(row)))
            for session in sorted({row['session'] for row in selected})},
        step_count=dict(median=median(steps) if steps else None, min=min(steps, default=None), max=max(steps, default=None)),
    )


def analyze(folders):
    rows, sessions = load(folders)
    names = list(sessions[0]['variants'])
    # 같은 세션·라운드의 두 변형을 짝지어 생성 호출 시간 합을 비교한다.
    pairs = Counter()
    for session, number in sorted({(row['session'], row['round']) for row in rows}):
        first, second = (sum(generation_ms(next(row for row in rows if row['session'] == session
                                               and row['round'] == number and row['variant'] == name)))
                         for name in names)
        pairs[f'{names[1]}_faster' if second < first else f'{names[0]}_faster'] += 1
    return dict(
        comparison=sessions[0].get('comparison'),
        sessions=[dict(id=s['session_id'], status=s['status'], started_at=s['started_at'], finished_at=s['finished_at'],
                       commit=s['environment']['commit'], dirty=s['environment']['dirty']) for s in sessions],
        variants={name: variant_summary([row for row in rows if row['variant'] == name]) for name in names},
        generation_pairs=dict(pairs),
    )


if __name__ == '__main__':
    result = {name: analyze(sorted(path for path in (HERE / name).glob('session-*') if path.is_dir()))
              for name in ('step-codes', 'reasoning-v2')}
    print(json.dumps(result, ensure_ascii=False, indent=1))
