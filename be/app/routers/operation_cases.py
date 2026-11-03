"""진행 중 행사의 운영 상황 확인."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.db.session import get_session
from app.models.auth import Account
from app.models.events import Event
from app.schemas.common import Envelope
from app.schemas.operation_cases import OperationCaseIn, OperationCaseList, OperationCaseOut
from app.services import operation_cases, planning_service

router = APIRouter(prefix='/api/v1/events/{event_id}/operation-cases', tags=['event-operations'])


async def _event(session: AsyncSession, event_id: str, account: Account):
    event = await session.get(Event, event_id)
    if event is None:
        raise planning_service.EventNotFound()
    member = await ensure_member(session, club_id=event.club_id, account=account)
    return event, member


@router.post('', response_model=Envelope[OperationCaseOut], status_code=201)
async def create(event_id: str, body: OperationCaseIn, account: Account = Depends(get_current_account),
                 session: AsyncSession = Depends(get_session)):
    event, member = await _event(session, event_id, account)
    case = await operation_cases.create(session, event, member, account, body.client_request_id, body.situation)
    return Envelope(data=await operation_cases.render(session, case, event, member))


@router.get('', response_model=OperationCaseList)
async def list_cases(event_id: str, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                     account: Account = Depends(get_current_account), session: AsyncSession = Depends(get_session)):
    event, member = await _event(session, event_id, account)
    rows, total = await operation_cases.list_cases(session, event_id, page, size)
    return OperationCaseList(data=[await operation_cases.render(session, row, event, member) for row in rows],
                             meta={'page': page, 'size': size, 'total_count': total})


@router.get('/{case_id}', response_model=Envelope[OperationCaseOut])
async def get_case(event_id: str, case_id: str, account: Account = Depends(get_current_account),
                   session: AsyncSession = Depends(get_session)):
    event, member = await _event(session, event_id, account)
    case = await operation_cases.get_case(session, event_id, case_id)
    return Envelope(data=await operation_cases.render(session, case, event, member))


@router.post('/{case_id}/question', response_model=Envelope[OperationCaseOut])
async def question(event_id: str, case_id: str, account: Account = Depends(get_current_account),
                   session: AsyncSession = Depends(get_session)):
    event, member = await _event(session, event_id, account)
    case = await operation_cases.run(session, event_id, case_id, account, 'question')
    return Envelope(data=await operation_cases.render(session, case, event, member))


@router.post('/{case_id}/result', response_model=Envelope[OperationCaseOut])
async def result(event_id: str, case_id: str, account: Account = Depends(get_current_account),
                 session: AsyncSession = Depends(get_session)):
    event, member = await _event(session, event_id, account)
    case = await operation_cases.run(session, event_id, case_id, account, 'result')
    return Envelope(data=await operation_cases.render(session, case, event, member))
