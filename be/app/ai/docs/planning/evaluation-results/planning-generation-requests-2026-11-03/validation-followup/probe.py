"""#239: 관찰된 인원 변경 채팅의 검증 실패를 3회만 추가 진단한다. 정책은 바꾸지 않는다."""
import asyncio
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

from app.ai import AIInvalidResponseError
from app.ai.config import AISettings
from app.ai.features.planning.generation import graph
from app.ai.scripts import check_planning_generation_requests as check
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, now, write_manifest
from app.ai.scripts.planning_latency_inputs import request_hashes
from app.ai.scripts.planning_latency_observation import install_observers


RULES = {
    '계획의 포함·제외 단계가 카탈로그와 맞지 않아요.':'catalog_partition',
    '계획의 세 묶음 순서가 맞지 않아요.':'phase_order',
    '단계 마감이 시작보다 빨라요.':'reversed_period',
    '행사 날짜가 미정이면 단계 날짜와 기한도 미정으로 남겨야 해요.':'dates_when_unknown',
    '단계에서 허용하지 않은 예정 행동이 있어요.':'action_type',
    '예정 행동의 기한이 단계 기간 밖에 있어요.':'action_due_outside_step',
    '행사 전에 할 단계가 행사 시작 뒤로 잡혔어요.':'before_event_after_start',
    '행사 당일 단계의 시작일이 현재 조건과 달라요.':'event_start_mismatch',
    '행사 당일 단계의 종료일이 현재 조건과 달라요.':'event_end_mismatch',
    '행사 뒤에 할 단계가 종료 전으로 잡혔어요.':'after_event_before_end',
    '제공하지 않은 기록 근거가 계획에 포함됐어요.':'unknown_fact_id',
}


async def main():
    source=Path('/tmp/planning-generation-239-real-20261103-01/fixture.json')
    directory=Path('/tmp/planning-generation-239-validation-20261103-01')
    raw=source.read_bytes()
    fixture=check.validate_fixture(json.loads(raw))
    settings=AISettings()
    settings.require_api()
    report=dict(status='running',started_at=now(),planned=3,finished=0,
        environment=execution_metadata('real_model',settings),fixture_sha256=hashlib.sha256(raw).hexdigest(),
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        purpose='기본 18요청의 인원 변경 채팅에서 invalid_plan 2건 관찰 후 세부 규칙을 새로 확인. 과거 실패의 소급 원인 아님.',
        changed='관측만 추가. 모델/프롬프트/처리기/검증/재시도 설정 동일.',rows=[])
    directory.mkdir(exist_ok=False)
    (directory/'fixture.json').write_bytes(raw)
    write_manifest(directory,report)
    original=graph.validate_plan
    failures=[]
    def validate(state):
        try:
            return original(state)
        except AIInvalidResponseError as error:
            # 검증기의 고정 문구만 enum으로 바꾼다. 공급자 오류/SDK/추론은 저장하지 않는다.
            failures.append(dict(rule=RULES.get(str(error),'unclassified_validator_error'),
                input=state['request'].model_dump(mode='json',exclude={'messages'}),
                composition=state['composition'].model_dump(mode='json')))
            raise
    try:
        with patch.object(graph,'validate_plan',validate), install_observers(), (directory/'attempts.jsonl').open('x') as stream:
            for number in range(1,4):
                failures.clear()
                request=check.make_request(fixture,'changed_headcount','chat',f'validation239-{number}')
                identity=dict(attempt_id=request.request_id,case_id='changed_headcount',route='chat',round=number)
                append_event(stream,dict(event='started',started_at=now(),**identity,
                    **request_hashes(request),request=request.model_dump(mode='json')))
                row,interrupted=await check.attempt(request)
                row.update(identity,validation_failures=list(failures))
                append_event(stream,dict(event='finished',finished_at=now(),**row))
                report['rows'].append({k:row.get(k) for k in ('attempt_id','outcome','generation_entered','stale_offer_id_used')}
                    | dict(validation_rules=[f['rule'] for f in failures]))
                report['finished']=number
                write_manifest(directory,report)
                print(json.dumps(report['rows'][-1],ensure_ascii=False),flush=True)
                if interrupted:
                    raise asyncio.CancelledError
                if row.get('stop_session'):
                    report['status']='stopped_'+row['stop_session']
                    break
                await asyncio.sleep(0.5)
            else:
                report['status']='completed'
    except (asyncio.CancelledError,KeyboardInterrupt):
        report['status']='interrupted'
        raise
    except BaseException:
        report['status']='runner_failed'
        raise
    finally:
        report['finished_at']=now()
        write_manifest(directory,report)


if __name__=='__main__':
    asyncio.run(main())
