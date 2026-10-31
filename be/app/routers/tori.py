"""인증된 소속의 토리 조회. 내용 변경이나 예약은 수행하지 않는다."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.core.deps import get_current_account, require_member
from app.core.exceptions import AIMisconfigured, AIUnavailable
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.reminders import ConfirmedTask
from app.schemas.common import Envelope
from app.schemas.reminders import ConfirmedTaskOut
from app.schemas.tori import ToriMessageIn, ToriMessageOut
from app.services import record_discovery_service

router = APIRouter(prefix='/api/v1/clubs/{club_id}/tori', tags=['tori'])
TZ = ZoneInfo('Asia/Seoul')


@router.post('/messages', response_model=Envelope[ToriMessageOut])
async def message(club_id: str, body: ToriMessageIn,
                  _member: Member = Depends(require_member),
                  account: Account = Depends(get_current_account),
                  session: AsyncSession = Depends(get_session)) -> Envelope[ToriMessageOut]:
    # 권한 확인 뒤 모델 호출 중 DB 연결을 점유하지 않는다.
    await session.commit()
    try:
        result = await ai.classify_tori_intent(ai.ToriIntentRequest(
            message=body.message, reference_date=datetime.now(TZ).date(), timezone='Asia/Seoul'))
    except ai.AIConfigError as error:
        raise AIMisconfigured() from error
    except ai.AIError as error:
        raise AIUnavailable() from error
    # 외부 호출 중 권한이 바뀔 수 있어 조회 전에 다시 검증한다.
    from app.core.deps import ensure_member
    await ensure_member(session, club_id=club_id, account=account)
    if result.intent == 'record_search':
        if not result.query or len(result.query) > 200:
            return Envelope(data=ToriMessageOut(intent='clarify', reply='찾을 자료를 조금 더 짧게 알려 주세요.'))
        records, total = await record_discovery_service.search_records(
            session, club_id=club_id, query=result.query.strip(), page=1, size=20)
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='자료 검색 결과를 확인해 주세요.',
                                             records=records, record_total_count=total))
    if result.intent == 'task_list':
        if result.scope is None or result.kind is None:
            return Envelope(data=ToriMessageOut(intent='clarify', reply='누구의 일정이나 할 일을 찾을지 알려 주세요.'))
        if result.date_to == date.max:
            return Envelope(data=ToriMessageOut(intent='clarify', reply='조회할 날짜 범위를 다시 알려 주세요.'))
        item_time = func.coalesce(ConfirmedTask.due_at, ConfirmedTask.scheduled_at)
        stmt = select(ConfirmedTask).where(ConfirmedTask.club_id == club_id, ConfirmedTask.status == 'ACTIVE')
        if result.scope == 'self':
            stmt = stmt.where(ConfirmedTask.assignee_account_id == account.id)
        if result.kind != 'all':
            stmt = stmt.where(ConfirmedTask.kind == result.kind.upper())
        if result.date_from:
            stmt = stmt.where(item_time >= datetime.combine(result.date_from, time.min, TZ).astimezone(UTC))
        if result.date_to:
            end = datetime.combine(result.date_to + timedelta(days=1), time.min, TZ).astimezone(UTC)
            stmt = stmt.where(item_time < end)
        rows = list((await session.scalars(stmt.order_by(item_time, ConfirmedTask.id).limit(21))).all())
        tasks = {'items': [ConfirmedTaskOut.model_validate(row) for row in rows[:20]],
                 'has_more': len(rows) > 20, 'scope': result.scope, 'kind': result.kind,
                 'date_from': result.date_from.isoformat() if result.date_from else None,
                 'date_to': result.date_to.isoformat() if result.date_to else None}
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='요청하신 범위의 확정된 일정과 할 일을 보여드릴게요. 회의나 행사별 구분은 적용되지 않아요.', tasks=tasks))
    if result.intent == 'event_planning':
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='행사 계획 화면으로 이동할 수 있어요.', navigation='/planning'))
    if result.intent == 'meeting':
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='회의 화면으로 이동할 수 있어요.', navigation='/meetings'))
    reply = '어떤 자료나 일정, 할 일을 찾을지 조금 더 알려 주세요.' if result.intent == 'clarify' else '아직 이 요청은 처리할 수 없어요. 자료 검색이나 확정된 일정 조회를 요청해 주세요.'
    return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply))
