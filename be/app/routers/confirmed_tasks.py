"""확정 일정·할 일 조회·변경·취소. OWNER/MANAGER만 예약을 바꾼다."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import WRITER_ROLES, require_club_role, require_member
from app.db.session import get_session
from app.models.clubs import Member
from app.schemas.common import Envelope
from app.schemas.reminders import ConfirmedTaskCancelIn, ConfirmedTaskOut, ConfirmedTaskUpdateIn
from app.services import reminder_service

router = APIRouter(prefix="/api/v1/clubs/{club_id}/confirmed-tasks", tags=["tasks"])


@router.get("", response_model=Envelope[list[ConfirmedTaskOut]])
async def list_confirmed_tasks(
    club_id: str,
    suggestion_id: str | None = Query(None, alias="suggestionId"),
    meeting_id: str | None = Query(None, alias="meetingId"),
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[ConfirmedTaskOut]]:
    items = await reminder_service.list_confirmed_tasks(
        session, club_id=club_id, suggestion_id=suggestion_id, meeting_id=meeting_id
    )
    return Envelope(data=[ConfirmedTaskOut.model_validate(item) for item in items])


@router.get("/{item_id}", response_model=Envelope[ConfirmedTaskOut])
async def get_confirmed_task(
    club_id: str,
    item_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ConfirmedTaskOut]:
    item = await reminder_service.get_confirmed_task(session, club_id=club_id, item_id=item_id)
    return Envelope(data=ConfirmedTaskOut.model_validate(item))


@router.patch("/{item_id}", response_model=Envelope[ConfirmedTaskOut])
async def update_confirmed_task(
    club_id: str,
    item_id: str,
    body: ConfirmedTaskUpdateIn,
    _member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ConfirmedTaskOut]:
    item = await reminder_service.update_confirmed_task(
        session, club_id=club_id, item_id=item_id, body=body
    )
    return Envelope(data=ConfirmedTaskOut.model_validate(item))


@router.post("/{item_id}/cancel", response_model=Envelope[ConfirmedTaskOut])
async def cancel_confirmed_task(
    club_id: str,
    item_id: str,
    body: ConfirmedTaskCancelIn,
    _member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ConfirmedTaskOut]:
    item = await reminder_service.cancel_confirmed_task(
        session, club_id=club_id, item_id=item_id, expected_version=body.expected_version
    )
    return Envelope(data=ConfirmedTaskOut.model_validate(item))
