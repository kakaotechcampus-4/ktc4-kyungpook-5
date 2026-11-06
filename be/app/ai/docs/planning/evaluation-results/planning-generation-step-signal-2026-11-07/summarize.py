"""measure_step_codes.py 결과를 사례별로 묶는다. 모델 호출 없음.

be/에서 실행: .venv/bin/python -I <이 파일> <report.json>

구간(모두 ms):
- 첫 글자 → 첫 코드: 「작성 중」이 된 뒤 첫 단계 이름이 붙기까지
- 첫 코드 → 마지막 코드: 단계 이름이 쌓이는 구간. 진행 기준은 p50 1,000 이상
- 마지막 코드 → 완료: 마지막 이름이 붙은 뒤 「작성 중」으로 기다리는 구간(제외 단계·가정·질문 작성 + 검증)
"""
import json
import statistics
import sys
from pathlib import Path


def quantile(values, q):
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def progress_ms(attempt, kind):
    return next((e['ms'] for e in attempt['events'] if e['kind'] == 'progress' and e['progress_kind'] == kind), None)


def gap(a, b):
    return round(b - a, 1) if None not in (a, b) else None


def rows(report):
    for attempt in report['attempts']:
        call = attempt['model_call'] or {}
        analysis = call.get('analysis') or {}
        ends = analysis.get('code_end_ms') or []
        first_text, finished = call.get('first_text'), progress_ms(attempt, 'generation_finished')
        first_code, last_code = (ends[0], ends[-1]) if ends else (None, None)
        writing = gap(first_text, finished)
        span = gap(first_code, last_code)
        yield dict(
            phase=attempt['phase'], round=attempt['round'], case=attempt['case'],
            ok=attempt['error'] is None and attempt['generation_status'] == 'generated',
            parsed=analysis.get('parsed'), steps_first=analysis.get('steps_first'),
            code_first=analysis.get('code_first_all'), matched=analysis.get('matched'),
            # 생성 성공일 때만 최종 초안과 비교할 수 있다
            same_as_preview=(analysis.get('codes') == attempt['preview_codes']) if attempt['preview_codes'] else None,
            steps=len(analysis.get('codes') or []),
            to_first_code=gap(first_text, first_code), code_span=span,
            after_last_code=gap(last_code, finished), writing=writing,
            span_share=round(span / writing, 2) if span is not None and writing else None,
        )


def main(path: Path):
    report = json.loads(path.read_text())
    table = list(rows(report))
    print(f"model={report['model']} commit={report['commit'][:7]} dirty={report['product_code_dirty']}")
    print('phase       round case ok steps_first code_first matched =preview steps  to_first  span  after_last  writing share')
    for r in table:
        flags = ' '.join(f"{'Y' if r[k] else ('-' if r[k] is None else 'N'):<{w}}" for k, w in
                         (('ok', 2), ('steps_first', 11), ('code_first', 10), ('matched', 7), ('same_as_preview', 8)))
        print(f"{r['phase']:<11} {r['round']:>5} {r['case']:<4} {flags} {r['steps']:>5} {r['to_first_code']!s:>9} "
              f"{r['code_span']!s:>6} {r['after_last_code']!s:>10} {r['writing']!s:>8} {r['span_share']!s:>5}")
    for case in ('G2', 'G1'):
        measured = [r for r in table if r['phase'] == 'measurement' and r['case'] == case]
        if not measured:
            continue
        print(f"\n{case}: 생성 성공 {sum(r['ok'] for r in measured)}/{len(measured)}, "
              f"steps 맨 앞 {sum(bool(r['steps_first']) for r in measured)}/{len(measured)}, "
              f"code 맨 앞 {sum(bool(r['code_first']) for r in measured)}/{len(measured)}, "
              f"위치 대조 {sum(bool(r['matched']) for r in measured)}/{len(measured)}, "
              f"최종 초안 순서 같음 {sum(bool(r['same_as_preview']) for r in measured)}/{sum(r['same_as_preview'] is not None for r in measured)}")
        for key in ('steps', 'to_first_code', 'code_span', 'after_last_code', 'writing', 'span_share'):
            values = [r[key] for r in measured if r[key] is not None]
            if values:
                print(f"  {key:<16} min {min(values):>9.2f}  p50 {statistics.median(values):>9.2f}  "
                      f"p95 {quantile(values, 0.95):>9.2f}  max {max(values):>9.2f}  (n={len(values)})")


main(Path(sys.argv[1]))
