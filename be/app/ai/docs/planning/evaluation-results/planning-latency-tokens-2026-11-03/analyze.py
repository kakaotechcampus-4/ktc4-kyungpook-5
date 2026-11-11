"""#263 보조 분석: 보존한 원본에서 모델 호출 시간과 토큰의 관계를 다시 계산한다.

모델·API 설정을 쓰지 않는다. be/에서 실행한다.
  .venv/bin/python app/ai/docs/planning/evaluation-results/planning-latency-tokens-2026-11-03/analyze.py \
      --output /tmp/planning-tokens-analysis.json

- 호출 시간 ~ 토큰 수의 최소제곱 직선과 상관계수 r. 인과나 보장이 아니라 관계의 크기를 보는 값이다.
- 10-28 기준값과 버튼 생성 초안 크기·생성 시간을 나란히 둔다. 두 날짜의 고정 입력 해시가 다르므로
  (749e4e3에서 날짜·장소를 명시적 미정으로 기록) 같은 조건의 전후 비교가 아니다.
"""
import argparse
import json
import statistics as st
from pathlib import Path

HERE = Path(__file__).parent
BASELINE = HERE.parent / 'planning-latency-real-2026-10-28'
STAGES = ('agent_model', 'generation_model')
KEYS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_input_tokens')


def measurement_rows(folder):
    for session in sorted(folder.glob('session-*')):
        for line in (session / 'attempts.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row.get('event') == 'finished' and row['phase'] == 'measurement':
                yield row


def fit(xs, ys):
    mx, my = st.fmean(xs), st.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return dict(intercept_seconds=my - slope * mx, seconds_per_1000_tokens=slope * 1000, r=sxy / (sxx * syy) ** .5)


def stage_analysis(rows, stage):
    calls = [(row['case_id'], span) for row in rows for span in row['observation']['spans']
             if span['stage'] == stage and span['usage'] and span['duration_ms'] is not None]
    usage = [span['usage'] for _, span in calls]
    seconds = [span['duration_ms'] / 1000 for _, span in calls]
    by_case = {}
    for case, span in calls:
        by_case.setdefault(case, []).append(span)
    return dict(
        calls_with_usage=len(calls),
        calls_with_cache_hit=sum(bool(item['cached_input_tokens']) for item in usage),
        reasoning_share_of_output=sum(item['reasoning_tokens'] or 0 for item in usage) / sum(item['output_tokens'] for item in usage),
        seconds_vs_tokens={key: fit([item[key] for item in usage], seconds)
                           for key in ('output_tokens', 'reasoning_tokens', 'input_tokens')},
        by_case={case: dict(calls=len(spans),
                            seconds_p50=st.median(span['duration_ms'] / 1000 for span in spans),
                            **{f'{key}_p50': st.median(span['usage'][key] or 0 for span in spans) for key in KEYS})
                 for case, spans in sorted(by_case.items())},
    )


def button_size(folder):
    """버튼 생성 성공 요청의 초안 크기와 생성 호출 시간. 입력 해시가 달라 참고용으로만 나란히 둔다."""
    items = [(row['output']['preview_bytes'], row['output']['step_count'], row['output']['action_count'],
              next(span for span in row['observation']['spans'] if span['stage'] == 'generation_model')['duration_ms'] / 1000)
             for row in measurement_rows(folder) if row['case_id'] == 'G2' and row['outcome'] == 'success']
    return dict(n=len(items), preview_bytes_p50=st.median(x[0] for x in items), step_count_p50=st.median(x[1] for x in items),
                action_count_p50=st.median(x[2] for x in items), generation_seconds_p50=st.median(x[3] for x in items),
                preview_bytes_per_second_p50=st.median(x[0] / x[3] for x in items))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = list(measurement_rows(HERE))
    result = dict(
        source='planning-latency-tokens-2026-11-03 measurement attempts',
        stages={stage: stage_analysis(rows, stage) for stage in STAGES},
        button_draft_size=dict(baseline_2026_10_28=button_size(BASELINE), current_2026_11_03=button_size(HERE)),
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
