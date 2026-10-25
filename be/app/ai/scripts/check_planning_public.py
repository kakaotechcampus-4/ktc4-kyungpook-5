"""공개 P1 함수의 실제 모델 연결 확인. be/에서 모듈로 실행하며 DB는 쓰지 않는다."""
import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.ai import (
    PlanningChatRequest, PlanningPreviewRequest, PlanningUserMessage,
    PlanningDraft, PlanningConditions, chat_planning, generate_planning_preview, parse_resume_state,
)
from app.ai.config import AISettings

AI_DIR = Path(__file__).resolve().parents[1]
MESSAGES = (
    '날짜는 아직 모르겠어. 일단 인원은 대략 50명으로 잡자.',
    '참가비 3만 원이면 어때? 아직 바꾸지는 말고 의견만 알려줘.',
    '일단 그렇게 잡자.',
    '현재 조건으로 흐름 초안을 만들 수 있을까? 아직 생성하지 말고 만들지 물어봐 줘.',
    '응, 만들어줘.',
)


async def run(output: Path) -> int:
    settings = AISettings()
    settings.require_api()
    if output.exists():
        raise ValueError('기존 결과를 덮어쓸 수 없습니다')
    sources = [AI_DIR / name for name in ('contracts.py','errors.py','facade.py','llm.py', 'config.py')]
    sources += sorted((AI_DIR / 'features/planning').rglob('*.py'))
    sources += sorted((AI_DIR / 'features/planning').rglob('*.md'))
    sources += [Path(__file__)]
    report = dict(
        status='running', started_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        model=settings.model, reference_date='2026-10-25',
        configuration='기본 공개 실행 설정. 프롬프트/모델 옵션 변경 없음',
        commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True)),
        sha256={str(p.relative_to(AI_DIR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        scope='합성 입력, 검색 port 미주입, JSON 메모리 저장/복원. 실제 DB/HTTP/FE 검증 아님',
        attempts=[], checks={},
    )
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    save()
    draft=PlanningDraft(conditions=PlanningConditions(event_type='MT',fee_per_person=25000))
    saved_json=None
    button_basis=None
    for index, text in enumerate(MESSAGES, 1):
        # BE가 다음 요청에서 저장 JSON을 읽는 상황을 매번 재현한다.
        state=parse_resume_state(saved_json) if saved_json else None
        request=PlanningChatRequest(request_id=f'public-turn-{index}',club_id='synthetic-club',
            event_id='synthetic-event',conversation_id='synthetic-conversation',base_revision=index-1,
            draft=draft,resume_state=state,reference_date=report['reference_date'],
            message=PlanningUserMessage(id=f'user-{index}',content=text))
        started=time.perf_counter()
        try:
            result=await chat_planning(request)
        except Exception as error:
            # 공급자 원문/인증값을 출력하지 않고 예외 타입만 남긴다.
            report['attempts'].append(dict(kind='chat',input=text,error_type=type(error).__name__,
                elapsed_seconds=round(time.perf_counter()-started,3)))
            report['status']='failed';save()
            print(f'chat {index}: {type(error).__name__}',flush=True)
            return 1
        saved_json=result.next_state.model_dump_json()
        restored=parse_resume_state(saved_json)
        draft=result.view.draft
        report['attempts'].append(dict(kind='chat',input=text,view=result.view.model_dump(mode='json'),
            elapsed_seconds=round(time.perf_counter()-started,3),state_bytes=len(saved_json.encode()),
            history_count=len(restored.payload.history),roundtrip_equal=restored==result.next_state,
            offer_status=restored.payload.generation.offer.status if restored.payload.generation.offer else None))
        if index==3:
            # 채팅 생성 전의 같은 조건을 버튼 경로에서도 독립적으로 확인한다.
            button_basis=(draft,saved_json)
        save();print(f'chat {index}: {report["attempts"][-1]["elapsed_seconds"]}s',flush=True)
    draft, snapshot=button_basis
    state=parse_resume_state(snapshot)
    started=time.perf_counter()
    try:
        button=await generate_planning_preview(PlanningPreviewRequest(
            request_id='public-button-1',club_id='synthetic-club',event_id='synthetic-event',
            conversation_id='synthetic-conversation',base_revision=3,draft=draft,resume_state=state,
            reference_date=report['reference_date']))
        report['attempts'].append(dict(kind='button',view=button.view.model_dump(mode='json'),
            elapsed_seconds=round(time.perf_counter()-started,3),
            history_unchanged=button.next_state.payload.history==state.payload.history,
            roundtrip_equal=parse_resume_state(button.next_state.model_dump_json())==button.next_state))
    except Exception as error:
        report['attempts'].append(dict(kind='button',error_type=type(error).__name__,
            elapsed_seconds=round(time.perf_counter()-started,3)))
        report['status']='failed';save();return 1
    turns=report['attempts']
    conditions=lambda i: turns[i]['view']['draft']['conditions']
    report['checks']={
        'multiple_conditions':conditions(0)['headcount']==50 and conditions(0)['fee_per_person']==25000,
        'date_deferred':'dates' in turns[0]['view']['draft']['deferred_topics'],
        'consultation_preserves_fee':conditions(1)['fee_per_person']==25000,
        'short_acceptance_updates_fee':conditions(2)['fee_per_person']==30000,
        'offer_without_generation':turns[3]['offer_status']=='pending' and turns[3]['view']['generation_result'] is None,
        'chat_generation':(turns[4]['view']['generation_result'] or {}).get('status')=='generated',
        'button_generation':(turns[5]['view']['generation_result'] or {}).get('status')=='generated',
        'button_no_fake_message':turns[5]['history_unchanged'],
        'json_roundtrip':all(t['roundtrip_equal'] for t in turns),
    }
    report['status']='passed' if all(report['checks'].values()) else 'failed'
    report['finished_at']=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    save();print(json.dumps(report['checks'],ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        return asyncio.run(run(args.output))
    except Exception as error:
        print(f'검증 실행 실패: {type(error).__name__}',flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
