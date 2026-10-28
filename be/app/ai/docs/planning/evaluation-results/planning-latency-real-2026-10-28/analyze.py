"""보존한 기준 측정에서 보조 진단을 재계산한다. 모델이나 API 설정은 사용하지 않는다."""
import argparse
import json
from collections import Counter
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
parser.add_argument('--output', type=Path, required=True)
args=parser.parse_args()
root=args.root
summary=json.loads((root/'combined-summary.json').read_text())
records=[]
for index in (1,2,3):
    for line in (root/f'session-{index:02d}'/'attempts.jsonl').read_text().splitlines():
        item=json.loads(line)
        if item['event']=='finished': records.append(item)
measured=[r for r in records if r['phase']=='measurement']
warmup=[r for r in records if r['phase']=='warmup']
case_data={}
for case,group in summary['groups']['measurement'].items():
    rows=[r for r in measured if r['case_id']==case]
    stage=group['observation']
    # 같은 완료 요청 집합의 평균을 사용한다. 부모 generation과 자식 구간을 합하지 않는다.
    total=group['completed_ms']['mean_ms']
    agent=stage['by_stage']['agent_model']['per_completed_request_total_ms']['mean_ms']
    generation=stage['by_stage']['generation']['per_completed_request_total_ms']['mean_ms']
    case_data[case]=dict(counts=group['counts'],success_rate=group['success_rate'],
        success_ms=group['success_ms'],completed_ms=group['completed_ms'],failure_ms=group['failure_ms'],
        failures=Counter((r.get('failure') or {}).get('category') for r in rows if r['outcome']=='failed'),
        failed_checks=Counter(key for r in rows for key,value in r.get('checks',{}).items() if not value),
        tool_counts=Counter(name for r in rows for name in r.get('tool_calls',[])),
        model_attempts=stage['model_call_attempts'],
        mean_request_breakdown_ms=dict(total=total,agent=agent,generation=generation,other=total-agent-generation),
        generation_errors=stage['by_stage']['generation']['error_calls'],
        validate_plan_ms=stage['by_stage']['validate_plan']['per_call_ms'],
        step_counts=Counter(r.get('output',{}).get('step_count') for r in rows if r['outcome']=='success'))
c2=[r for r in measured if r['case_id']=='C2']
c2_diagnostics=dict(
    headcount_60=sum(r.get('result',{}).get('view',{}).get('draft',{}).get('conditions',{}).get('headcount')==60 for r in c2),
    conditions_match=sum(r.get('checks',{}).get('conditions_match') is True for r in c2),
    no_generation=sum(r.get('checks',{}).get('no_generation') is True for r in c2),
    metadata_status_counts=Counter(r.get('result',{}).get('view',{}).get('draft',{}).get('condition_meta',{}).get('headcount',{}).get('status') for r in c2),
    deferred_topics_counts=Counter(','.join(r.get('result',{}).get('view',{}).get('draft',{}).get('deferred_topics',[])) or '(none)' for r in c2),
    failed_check_combinations=Counter(','.join(k for k,v in r.get('checks',{}).items() if not v) or '(none)' for r in c2))
retries=[]
for r in measured:
    roots=[s for s in r['observation']['spans'] if s['stage']=='generation']
    if len(roots)>1:
        retries.append(dict(request_id=r['attempt_id'],case=r['case_id'],outcome=r['outcome'],
            request_ms=r['ai_request_ms'],roots=[dict(duration_ms=s['duration_ms'],outcome=s['outcome'],code=s['failure_code']) for s in roots],
            model_attempts=r['observation']['model_call_attempts']))
examples={}
for case in ('C1','C2','G1','G2'):
    options=[r for r in measured if r['case_id']==case and r['outcome']=='success']
    # p50 자체를 실제 요청처럼 만들지 않고, 가장 가까운 성공 요청 한 건을 고른다.
    median=summary['groups']['measurement'][case]['success_ms']['p50_ms']
    selected=min(options,key=lambda r:abs(r['ai_request_ms']-median))
    examples[case]=dict(request_id=selected['attempt_id'],ai_request_ms=selected['ai_request_ms'],
        model_attempts=selected['observation']['model_call_attempts'],spans=selected['observation']['spans'])
analysis=dict(kind='real_model_baseline_analysis',model=summary['model'],case_results=case_data,c2_diagnostics=c2_diagnostics,
    retries=retries,examples=examples,measurement_requests=len(measured),warmup_requests=len(warmup),
    successful=sum(r['outcome']=='success' for r in measured),failed=sum(r['outcome']=='failed' for r in measured),
    normal_returns=sum(r['returned_normally'] for r in measured),
    observed_model_attempts={phase:{kind:sum(r['observation']['model_call_attempts'][kind] for r in rows) for kind in ('agent_model','generation_model')}
        for phase,rows in [('measurement',measured),('warmup',warmup)]},
    observed_span_error_codes=Counter(s['failure_code'] for r in measured for s in r['observation']['spans'] if s['outcome']=='error'))
with args.output.open('x') as stream:
    json.dump(analysis,stream,ensure_ascii=False,indent=2,allow_nan=False)
    stream.write('\n')
print(f'보조 진단 저장: {args.output}')
