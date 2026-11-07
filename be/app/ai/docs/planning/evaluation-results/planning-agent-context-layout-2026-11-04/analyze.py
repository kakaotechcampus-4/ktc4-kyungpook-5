"""#269 결과 분석: 보존한 원본에서 v7/v8을 다시 집계한다.

모델·API 설정을 쓰지 않는다. be/에서 실행한다.
  .venv/bin/python app/ai/docs/planning/evaluation-results/planning-agent-context-layout-2026-11-04/analyze.py \
      --output /tmp/planning-layout-analysis.json

- 사례별 요청 집계와 대조 사례는 비교 실행기의 summarize를 그대로 쓴다.
- 대화 호출 전체 분포, 캐시가 걸린 호출 수, 세션별 값, 같은 라운드·사례 쌍의 차이를 더한다.
- G1에서 대화 모델이 고른 생성 Tool 인자를 모아, 생성 입력이 두 변형에서 같았는지 확인한다.
"""
import argparse
import json
import statistics as st
from collections import Counter
from pathlib import Path

from app.ai.scripts.compare_agent_context_layout import CASE_IDS, VARIANTS, summarize
from app.ai.scripts.planning_latency_summary import distribution

HERE = Path(__file__).parent


def finished_rows(folder):
    for session in sorted(folder.glob('session-*')):
        for line in (session / 'attempts.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row['event'] == 'finished':
                yield session.name, row


def agent_spans(row):
    return [span for span in row['observation']['spans'] if span['stage'] == 'agent_model' and span['outcome'] == 'ok']


def agent_calls(rows):
    spans = [span for row in rows for span in agent_spans(row)]
    return dict(call_ms=distribution(span['duration_ms'] for span in spans),
                calls_with_cache_hit=sum(bool(span['usage'] and span['usage']['cached_input_tokens']) for span in spans),
                calls=len(spans))


def paired(rows):
    """같은 세션·라운드·사례의 v7과 v8을 짝지어 요청 1건의 대화 호출 시간 합을 비교한다."""
    pairs = {}
    for session, row in rows:
        total = sum(span['duration_ms'] for span in row['observation']['spans'] if span['stage'] == 'agent_model') / 1000
        pairs.setdefault((session, row['round'], row['case_id']), {})[row['variant']] = total
    diffs = [pair['v7'] - pair['v8'] for pair in pairs.values() if len(pair) == 2]
    return dict(pairs=len(diffs), v7_minus_v8_seconds_median=st.median(diffs), v7_minus_v8_seconds_mean=st.fmean(diffs),
                pairs_v8_faster=sum(diff > 0 for diff in diffs))


def generation_tool_args(rows):
    """G1에서 대화 모델이 고른 Tool과 인자. 생성 입력은 이 인자와 초안·이력의 글로만 만들어진다."""
    counts = Counter()
    for _, row in rows:
        if row['case_id'] != 'G1' or not row.get('result'):
            continue
        calls = [call for message in row['result']['next_state']['payload']['history']
                 if message['role'] == 'assistant' for call in message['tool_calls']]
        last = calls[-1]
        counts[(row['variant'], row['outcome'], last['name'], json.dumps(last['args'], ensure_ascii=False, sort_keys=True))] += 1
    return [dict(variant=v, outcome=o, tool=t, args=json.loads(a), requests=n) for (v, o, t, a), n in sorted(counts.items())]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = list(finished_rows(HERE))
    measured = [(session, row) for session, row in rows if row['phase'] == 'measurement']
    sessions = sorted({session for session, _ in measured})
    result = dict(
        source='planning-agent-context-layout-2026-11-04 attempts',
        summary=summarize([row for _, row in rows]),
        agent_calls={variant: agent_calls([row for _, row in measured if row['variant'] == variant]) for variant in VARIANTS},
        agent_calls_by_session={session: {variant: agent_calls([row for s, row in measured if s == session and row['variant'] == variant])
                                          for variant in VARIANTS} for session in sessions},
        paired_agent_seconds=paired(measured),
        g1_generation_tool_args=generation_tool_args(measured),
        cases=CASE_IDS,
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(agent_calls=result['agent_calls'], paired=result['paired_agent_seconds'],
                          g1_tool_args=result['g1_generation_tool_args']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
