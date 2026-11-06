"""measure_adoption.py 결과를 사례·경로별로 묶는다. 모델 호출 없음.

be/에서 실행: .venv/bin/python -I <이 파일> <adoption-report.json>
"""
import json
import statistics
import sys
from pathlib import Path



def quantile(values, q):
    # 선형 보간(R7). summarize.py와 같은 방식.
    values = sorted(values)
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def main(path: Path):
    report = json.loads(path.read_text())
    measured = [a for a in report['attempts'] if a['phase'] == 'measurement']
    print(f"model={report['model']} commit={report['commit'][:7]} dirty={report['product_code_dirty']} rounds={report['rounds']}")
    total = lambda a: next(e['ms'] for e in a['events'] if e['kind'] == 'end')
    # 생성 구간: generation_started → generation_finished. G1 전체에 섞인 대화 모델 호출을 뺀 값(진단용)
    def span(a):
        at = {e['progress_kind']: e['ms'] for e in a['events'] if e['kind'] == 'progress'}
        return at['generation_finished'] - at['generation_started']
    kinds = lambda a: [e['progress_kind'] for e in a['events'] if e['kind'] == 'progress' and e['progress_kind'].startswith('generation_')]
    for case in ('G2', 'G1'):
        by_path, p50 = {}, {}
        for path_name in ('invoke', 'stream'):
            rows = [a for a in measured if a['case'] == case and a['path'] == path_name]
            by_path[path_name] = {a['round']: a for a in rows}
            times = [total(a) for a in rows]
            p50[path_name] = statistics.median(times)
            ok = sum(a['error'] is None and a['generation_status'] == 'generated' for a in rows)
            writing = [kinds(a).count('generation_writing') for a in rows]
            order_ok = sum(kinds(a) == ['generation_started', 'generation_writing', 'generation_finished'] for a in rows)
            print(f"{case} {path_name:<6} 생성 성공 {ok}/{len(rows)}  단계 수 {sorted((a['steps'] for a in rows), key=lambda v: (v is None, v or 0))}  "
                  f"전체 p50 {statistics.median(times):,.0f}  p95 {quantile(times, 0.95):,.0f}  "
                  f"생성 구간 p50 {statistics.median(span(a) for a in rows):,.0f}  "
                  f"writing 횟수 {writing}  시작→작성→끝 순서 {order_ok}/{len(rows)}")
        diffs = [total(by_path['stream'][r]) - total(by_path['invoke'][r])
                 for r in by_path['invoke'] if r in by_path['stream']]
        faster = sum(d < 0 for d in diffs)
        span_diffs = [span(by_path['stream'][r]) - span(by_path['invoke'][r])
                      for r in by_path['invoke'] if r in by_path['stream']]
        print(f"{case} 전체 p50 차이(새−기존) {p50['stream'] - p50['invoke']:+,.0f}ms  (기준: +500ms 이내)")
        print(f"{case} 같은 라운드 짝 {len(diffs)}개: 새 경로가 빠른 짝 {faster}, 차이(새−기존) 중앙값 {statistics.median(diffs):+,.0f}ms, "
              f"생성 구간만 {statistics.median(span_diffs):+,.0f}ms")


main(Path(sys.argv[1]))
