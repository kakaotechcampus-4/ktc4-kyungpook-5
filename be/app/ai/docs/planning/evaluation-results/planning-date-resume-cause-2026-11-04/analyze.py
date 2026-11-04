"""#274 측정 원본(2단계·3단계)을 다시 집계한다. 모델이나 API 설정을 쓰지 않는다.

  .venv/bin/python app/ai/docs/planning/evaluation-results/planning-date-resume-cause-2026-11-04/analyze.py \
    --output /tmp/planning-date-resume-analysis.json
"""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
FOLDERS = ('step2-date-resume', 'step3-controls')
VARIANTS = ('single', 'multi')


def finished(folder):
    rows = []
    for line in (HERE / folder / 'attempts.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['event'] == 'finished':
            rows.append(row)
    return rows


def condition_args(row):
    """실패 원인을 읽기 쉽게: 조건 변경 Tool마다 바꾼 필드, 보류/재개 주제와 근거, 실행 결과."""
    out = []
    for number, batch in enumerate(row['tool_trace'] or [], 1):
        for call in batch:
            if call['name'] != 'update_event_conditions':
                continue
            args = call['args']
            out.append(dict(
                response=number, status=call['status'],
                changes=[(item.get('change') or {}).get('field') or item.get('field') for item in args.get('changes') or []],
                defer_topics=[(item['topic'], item['evidence']['quote']) for item in args.get('defer_topics') or []],
                resume_topics=[(item['topic'], item['evidence']['quote']) for item in args.get('resume_topics') or []]))
    return out


def group(rows):
    by = defaultdict(list)
    for row in rows:
        by[(row['case_id'], row['variant'])].append(row)
    result = {}
    for (case_id, variant), chosen in sorted(by.items()):
        traces = [row['tool_trace'] for row in chosen if row.get('tool_trace') is not None]
        result.setdefault(case_id, {})[variant] = dict(
            started=len(chosen), passed=sum(row['passed'] for row in chosen),
            errors=dict(Counter(row['error'] for row in chosen if row.get('error'))),
            dates_handling={outcome: dict(Counter(row['dates_handling'] for row in chosen
                                                  if row['passed'] == (outcome == 'passed')))
                            for outcome in ('passed', 'failed')},
            responses_with_tools=dict(Counter(len(trace) for trace in traces)),
            bundled=sum(any(len(batch) > 1 for batch in trace) for trace in traces),
            request_p50_seconds=round(statistics.median(row['ai_request_ms'] for row in chosen) / 1000, 2),
            failures=[dict(attempt_id=row['attempt_id'], dates_handling=row.get('dates_handling'),
                           conditions=condition_args(row), reply=row.get('reply'))
                      for row in chosen if not row['passed']],
            # 상태는 날짜를 재개했는데 답변에 "나중"이 있는 요청. 자동으로 골라 사람이 읽고 판단한다.
            resumed_but_reply_mentions_later=[dict(attempt_id=row['attempt_id'], reply=row['reply'])
                                              for row in chosen if row.get('dates_handling') == 'resumed'
                                              and '나중' in (row.get('reply') or '')])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=HERE / 'analysis.json')
    args = parser.parse_args()
    analysis = {}
    for folder in FOLDERS:
        session = json.loads((HERE / folder / 'session.json').read_text())
        analysis[folder] = dict(
            commit=session['environment']['commit'], dirty=session['environment']['dirty'],
            started_at=session['started_at'], finished_at=session['finished_at'],
            model=session['environment']['model'], prompt_version=session['prompt_version'],
            cases=group(finished(folder)))
    args.output.write_text(json.dumps(analysis, ensure_ascii=False, indent=1) + '\n')
    for folder, data in analysis.items():
        print(folder, data['commit'][:7])
        for case_id, variants in data['cases'].items():
            print(f"  {case_id:24s}", '  '.join(f"{v} {variants[v]['passed']}/{variants[v]['started']}"
                                               for v in VARIANTS if v in variants))


if __name__ == '__main__':
    main()
