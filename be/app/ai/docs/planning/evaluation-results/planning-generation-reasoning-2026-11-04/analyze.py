"""#264 결과 분석: 보존한 원본에서 생성 모델 추론 깊이 default/low를 다시 집계한다.

모델·API 설정을 쓰지 않는다. be/에서 실행한다.
  .venv/bin/python app/ai/docs/planning/evaluation-results/planning-generation-reasoning-2026-11-04/analyze.py \
      --output /tmp/planning-reasoning-analysis.json

- 변형별 요청 집계·단계 수·검증 거절 규칙은 비교 실행기의 summarize를 그대로 쓴다.
- 생성 호출 1번의 시간과 토큰 분포, 세션별 생성 호출 p50(채택 기준 2), 같은 세션·라운드 쌍의 차이를 더한다.
- 채택 기준 세 가지(#264 이슈에 측정 전에 적은 것)의 판정을 함께 계산한다.
- 검증 거절 자료(validation/)에서 카탈로그 밖 코드나 빠진 코드가 무엇이었는지 모은다.
"""
import argparse
import json
import statistics as st
import sys
from pathlib import Path

from app.ai.scripts.compare_generation_reasoning import VARIANTS, summarize
from app.ai.scripts.planning_latency_summary import distribution, token_distribution

HERE = Path(__file__).parent
TOKENS = ('input_tokens', 'output_tokens', 'reasoning_tokens', 'cached_input_tokens')


def finished_rows(folder):
    for session in sorted(folder.glob('session-*')):
        if not session.is_dir():
            continue
        for line in (session / 'attempts.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row['event'] == 'finished':
                yield session.name, row


def generation_spans(row):
    return [span for span in row['observation']['spans'] if span['stage'] == 'generation_model']


def generation_calls(rows):
    """완료된 생성 호출 1번의 시간과 토큰. 실패한 호출도 응답을 받았다면 토큰이 남는다."""
    spans = [span for row in rows for span in generation_spans(row) if span['duration_ms'] is not None]
    usage = [span['usage'] for span in spans if span.get('usage')]
    result = dict(calls=len(spans), call_ms=distribution(span['duration_ms'] for span in spans),
                  usage_observed=len(usage))
    for key in TOKENS:
        values = [item[key] for item in usage if item.get(key) is not None]
        result[key] = token_distribution(values)
    outputs = [item for item in usage if item.get('reasoning_tokens') is not None]
    result['reasoning_share_of_output'] = (sum(item['reasoning_tokens'] for item in outputs)
                                           / sum(item['output_tokens'] for item in outputs)) if outputs else None
    return result


def paired(rows):
    """같은 세션·라운드의 default와 low를 짝지어 생성 호출 시간을 비교한다."""
    pairs = {}
    for session, row in rows:
        spans = generation_spans(row)
        if len(spans) == 1 and spans[0]['duration_ms'] is not None:
            pairs.setdefault((session, row['round']), {})[row['variant']] = spans[0]['duration_ms'] / 1000
    diffs = [pair['default'] - pair['low'] for pair in pairs.values() if len(pair) == 2]
    return dict(pairs=len(diffs), default_minus_low_seconds_median=st.median(diffs) if diffs else None,
                default_minus_low_seconds_mean=st.fmean(diffs) if diffs else None,
                pairs_low_faster=sum(diff > 0 for diff in diffs))


def violation_details(folder):
    """catalog_partition 거절이 어떤 코드 때문이었는지. 저장한 초안과 위반 정보만 읽는다."""
    details = []
    for path in sorted(folder.glob('session-*/validation/*.json')):
        data = json.loads(path.read_text())
        violation = data['violation']
        item = dict(file=str(path.relative_to(folder)), rule=violation['rule'])
        if violation['rule'] == 'catalog_partition':
            catalog = set(violation['expected']['catalog_codes'])
            included, excluded = violation['actual']['included'], violation['actual']['excluded']
            item.update(outside_catalog=sorted((set(included) | set(excluded)) - catalog),
                        outside_catalog_in_excluded=sorted(set(excluded) - catalog),
                        missing=sorted(catalog - set(included) - set(excluded)),
                        duplicated=len(included) + len(excluded) - len(set(included) | set(excluded)))
        details.append(item)
    return details


def criteria(summary, by_session):
    """#264 이슈에 측정 전에 적은 채택 기준. 셋 다 참이어야 low를 채택한다."""
    passed = {name: summary[name]['latency']['counts']['success'] for name in VARIANTS}
    steps = {name: summary[name]['success_step_count']['median'] for name in VARIANTS}
    p50 = {session: {name: values[name]['call_ms']['p50_ms'] for name in VARIANTS} for session, values in by_session.items()}
    checks = dict(
        pass_count_not_lower=passed['low'] >= passed['default'],
        generation_p50_lower_every_session=all(v['low'] is not None and v['default'] is not None and v['low'] < v['default']
                                               for v in p50.values()),
        step_count_median_not_lower=steps['low'] is not None and steps['default'] is not None and steps['low'] >= steps['default'],
    )
    return dict(passed=passed, step_count_median=steps, generation_p50_by_session=p50, checks=checks,
                adopt_low=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--folder', type=Path, default=HERE)
    args = parser.parse_args()
    rows = list(finished_rows(args.folder))
    measured = [(session, row) for session, row in rows if row['phase'] == 'measurement']
    sessions = sorted({session for session, _ in measured})
    summary = summarize([row for _, row in rows])
    by_session = {session: {name: generation_calls([row for s, row in measured if s == session and row['variant'] == name])
                            for name in VARIANTS} for session in sessions}
    result = dict(
        source='planning-generation-reasoning-2026-11-04 attempts',
        summary=summary,
        generation_calls={name: generation_calls([row for _, row in measured if row['variant'] == name]) for name in VARIANTS},
        generation_calls_by_session=by_session,
        paired_generation_seconds=paired(measured),
        criteria=criteria(summary, by_session),
        violations=violation_details(args.folder),
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    json.dump(dict(criteria=result['criteria'], paired=result['paired_generation_seconds']),
              sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == '__main__':
    main()
