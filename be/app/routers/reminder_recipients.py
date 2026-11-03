"""알림의 수신자 선택에 필요한 최소 명단. 이메일·전화 등은 노출하지 않는다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_member
from app.db.session import get_session
from app.models.clubs import Member
from app.schemas.common import Envelope
from app.schemas.reminders import ReminderRecipientOut
from app.services.reminder_service import list_recipients

router = APIRouter(prefix="/api/v1/clubs/{club_id}/reminder-recipients", tags=["tasks"])


@router.get("", response_model=Envelope[list[ReminderRecipientOut]])
async def reminder_recipients(
    club_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[ReminderRecipientOut]]:
    return Envelope(data=await list_recipients(session, club_id=club_id))
