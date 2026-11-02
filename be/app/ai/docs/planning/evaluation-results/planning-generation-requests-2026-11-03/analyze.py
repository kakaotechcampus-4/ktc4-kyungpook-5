"""#239 원본의 요청 짝·입력/코드 해시·구간 관측과 집계를 모델 없이 검산한다."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from app.ai.scripts import check_planning_generation_requests as check
from app.ai.scripts.planning_latency_inputs import request_hashes
from app.ai.scripts.planning_latency_observation import validate_observation


def analyze(directory):
    session=json.loads((directory/'session.json').read_text())
    fixture=check.validate_fixture(json.loads((directory/'fixture.json').read_text()))
    events=[json.loads(line) for line in (directory/'attempts.jsonl').read_text().splitlines()]
    starts=[x for x in events if x['event']=='started']
    finishes=[x for x in events if x['event']=='finished']
    assert session['status']=='completed'
    assert session['finished']==session['planned']==len(starts)==len(finishes)==18
    assert len({x['attempt_id'] for x in starts})==18
    assert [x['attempt_id'] for x in starts]==[x['attempt_id'] for x in finishes]
    assert [(x['round'],x['case_id'],x['route']) for x in starts]==check.schedule(3)
    assert hashlib.sha256((directory/'fixture.json').read_bytes()).hexdigest()==session['fixture_sha256']
    assert (directory/'fixture.json').read_bytes()==check.DEFAULT_FIXTURE.read_bytes()
    for start,finish in zip(starts,finishes,strict=True):
        expected=check.make_request(fixture,start['case_id'],start['route'],start['attempt_id'])
        assert start['request']==expected.model_dump(mode='json')
        for key,value in request_hashes(expected).items():
            assert start[key]==value
        validate_observation(finish['observation'],finish['ai_request_ms'])
    for case_id in check.CASE_IDS:
        selected=[x for x in starts if x['case_id']==case_id]
        assert len({json.dumps(x['request']['draft'],sort_keys=True) for x in selected})==1
        assert len({json.dumps(x['request']['resume_state'],sort_keys=True) for x in selected})==1
        assert all(x['request']['resume_state']['payload']['generation']['preview'] is None for x in selected)
    assert check.summarize(finishes)==session['summary']
    assert all(hashlib.sha256((check.AI_DIR/path).read_bytes()).hexdigest()==value
               for path,value in session['environment']['source_sha256'].items())
    assert hashlib.sha256(Path(check.__file__).read_bytes()).hexdigest()==session['evaluator_sha256']
    groups={}
    for case_id in check.CASE_IDS:
        groups[case_id]={}
        for route in check.ROUTES:
            rows=[r for r in finishes if r['case_id']==case_id and r['route']==route]
            groups[case_id][route]=dict(session['summary'][case_id][route],
                generation_status=dict(Counter(r.get('generation_status') or 'not_returned' for r in rows)),
                model_calls={stage:sum(r['observation']['model_call_attempts'][stage] for r in rows)
                             for stage in ('agent_model','generation_model')},
                intermediate_errors=dict(Counter(s['failure_code'] for r in rows
                    for s in r['observation']['spans'] if s['outcome']=='error')))
    return dict(model=session['environment']['model'],commit=session['environment']['commit'],
        verified=dict(paired_events=36,identical_route_snapshots=True,no_success_reuse=True,
                      hashes_match=True,observations_valid=True,summary_matches=True),
        counts=dict(requests=18,success=sum(r['outcome']=='success' for r in finishes),
                    failed=sum(r['outcome']=='failed' for r in finishes),
                    stale_offer_id_used=sum(r['stale_offer_id_used'] for r in finishes)),
        groups=groups,
        failures=[dict(attempt_id=r['attempt_id'],failure_category=r.get('failure_category'),
                       checks=r.get('checks'),tool_activity=r['tool_activity'],reply=r.get('reply'))
                  for r in finishes if r['outcome']!='success'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=analyze(args.directory)
    with args.output.open('x') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps({k:report[k] for k in ('model','commit','verified','counts','groups')},ensure_ascii=False,indent=2))
