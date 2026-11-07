"""#265 single/multi 측정 원본을 다시 집계한다. 모델이나 API 설정을 쓰지 않는다.

  .venv/bin/python app/ai/docs/planning/evaluation-results/planning-parallel-tool-calls-2026-11-04/analyze.py \
    --output /tmp/planning-parallel-analysis.json
"""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SESSIONS = ('session-01', 'session-02', 'session-03')
EXTRA = 'date-resume-extra'
VARIANTS = ('single', 'multi')


def percentile(values, p):
    """R7(선형 보간). 측정기 집계와 같은 방식이다."""
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * p
    low = int(k)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (k - low)


def finished(folder):
    rows = []
    for line in (HERE / folder / 'attempts.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['event'] == 'finished':
            rows.append(dict(row, session=folder))
    return rows


def agent_calls(row):
    return [span for span in row['observation']['spans'] if span['stage'] == 'agent_model']


def round2(value):
    return None if value is None else round(value, 2)


def latency(rows):
    result = {}
    for variant in VARIANTS:
        chosen = [row for row in rows if row['variant'] == variant]
        seconds = [row['ai_request_ms'] / 1000 for row in chosen if row['outcome'] == 'success']
        calls = [agent_calls(row) for row in chosen]
        by_position = []
        for index in range(max(len(item) for item in calls)):
            spans = [item[index] for item in calls if len(item) > index]
            by_position.append(dict(
                position=index + 1, n=len(spans),
                seconds_p50=round2(percentile([s['duration_ms'] / 1000 for s in spans], 0.5)),
                output_tokens_p50=percentile([s['usage']['output_tokens'] for s in spans], 0.5)))
        every = [span['duration_ms'] / 1000 for item in calls for span in item]
        result[variant] = dict(
            started=len(chosen), success=len(seconds),
            p50=round2(percentile(seconds, 0.5)), p95=round2(percentile(seconds, 0.95)),
            mean=round2(statistics.mean(seconds)),
            session_p50={folder: round2(percentile([row['ai_request_ms'] / 1000 for row in chosen
                                                    if row['session'] == folder and row['outcome'] == 'success'], 0.5))
                         for folder in SESSIONS},
            agent_calls_per_request=dict(Counter(len(item) for item in calls)),
            agent_call_seconds=dict(n=len(every), p50=round2(percentile(every, 0.5)), p95=round2(percentile(every, 0.95))),
            by_position=by_position,
            bundled=sum(any(len(batch) > 1 for batch in row['tool_batches']) for row in chosen),
            patterns=dict(Counter(' | '.join('+'.join(batch) for batch in row['tool_batches']) for row in chosen)))
    pairs = []
    for folder in SESSIONS:
        for number in range(1, 11):
            pair = {row['variant']: row['ai_request_ms'] / 1000 for row in rows
                    if row['session'] == folder and row['round'] == number}
            pairs.append(pair['single'] - pair['multi'])
    result['paired'] = dict(n=len(pairs), median_saving=round2(statistics.median(pairs)),
                            mean_saving=round2(statistics.mean(pairs)), multi_faster=sum(p > 0 for p in pairs))
    return result


def controls(rows):
    table = {}
    for row in rows:
        group = table.setdefault(row['case_id'], {}).setdefault(row['variant'], dict(started=0, passed=0, failed_checks=Counter()))
        group['started'] += 1
        group['passed'] += row['passed']
        group['failed_checks'].update(key for key, ok in row['checks'].items() if not ok)
    return {case: {variant: dict(group, failed_checks=dict(group['failed_checks'])) for variant, group in variants.items()}
            for case, variants in table.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('출력 파일이 이미 있습니다')
    rows = [row for folder in SESSIONS for row in finished(folder)]
    extra = finished(EXTRA)
    analysis = dict(
        latency=latency([row for row in rows if row['phase'] == 'measurement']),
        controls=controls([row for row in rows if row['phase'] == 'control']),
        date_resume_extra=controls(extra)['date_resume'],
    )
    args.output.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(latency={v: {k: analysis['latency'][v][k] for k in ('success', 'p50', 'p95', 'bundled')}
                                   for v in VARIANTS}, paired=analysis['latency']['paired'],
                          date_resume_extra={v: g['passed'] for v, g in analysis['date_resume_extra'].items()}),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
