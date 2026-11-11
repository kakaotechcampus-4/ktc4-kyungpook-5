"""measure_writing_start.py 결과를 사례별로 묶는다. 모델 호출 없음.

be/에서 실행: .venv/bin/python -I <이 파일> <report.json>

화면 기준 구간(진행 신호 시각 기준):
- 생각 중 = generation_started 신호 → 첫 글자 조각
- 작성 중 = 첫 글자 조각 → generation_finished 신호
"""
import json
import statistics
import sys
from pathlib import Path


def quantile(values, q):
    # 선형 보간(R7). #266 측정과 같은 방식.
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def progress_ms(attempt, kind):
    return next((e['ms'] for e in attempt['events'] if e['kind'] == 'progress' and e['progress_kind'] == kind), None)


def rows(report):
    for attempt in report['attempts']:
        call = attempt['model_call'] or {}
        started, finished = progress_ms(attempt, 'generation_started'), progress_ms(attempt, 'generation_finished')
        first_text = call.get('first_text')
        yield dict(
            phase=attempt['phase'], round=attempt['round'], case=attempt['case'],
            ok=attempt['error'] is None and attempt['generation_status'] == 'generated',
            thinking=round(first_text - started, 1) if None not in (first_text, started) else None,
            writing=round(finished - first_text, 1) if None not in (first_text, finished) else None,
            model_first_chunk=call['first_chunk'] - call['start'] if call.get('first_chunk') else None,
            reasoning_chunks=call.get('reasoning_chunks'), text_chunks=call.get('text_chunks'),
            text_span=round(call['last_text'] - first_text, 1) if first_text else None,
            output_tokens=(call.get('usage') or {}).get('output'),
            reasoning_tokens=(call.get('usage') or {}).get('reasoning'),
            total=next(e['ms'] for e in attempt['events'] if e['kind'] == 'end'),
        )


def main(path: Path):
    report = json.loads(path.read_text())
    table = list(rows(report))
    print(f"model={report['model']} commit={report['commit'][:7]} dirty={report['product_code_dirty']}")
    print('phase       round case ok  thinking  writing  text_chunks reasoning_chunks  out/reason tokens  total')
    for r in table:
        print(f"{r['phase']:<11} {r['round']:>5} {r['case']:<4} {'Y' if r['ok'] else 'N':<3} "
              f"{r['thinking'] or '-':>8} {r['writing'] or '-':>8} {r['text_chunks']!s:>12} {r['reasoning_chunks']!s:>16} "
              f"{r['output_tokens']!s:>6}/{r['reasoning_tokens']!s:<6} {r['total']:>10}")
    for case in ('G2', 'G1'):
        measured = [r for r in table if r['phase'] == 'measurement' and r['case'] == case]
        if not measured:
            continue
        print(f"\n{case}: 생성 성공 {sum(r['ok'] for r in measured)}/{len(measured)}")
        for key in ('thinking', 'writing', 'text_chunks', 'text_span', 'total'):
            values = [r[key] for r in measured if r[key] is not None]
            if values:
                print(f"  {key:<12} min {min(values):>9.1f}  p50 {statistics.median(values):>9.1f}  "
                      f"p95 {quantile(values, 0.95):>9.1f}  max {max(values):>9.1f}  (n={len(values)})")


main(Path(sys.argv[1]))
