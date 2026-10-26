"""동아리 기록 엔드포인트. 이번에는 업로드와 단건 조회만 연다(meeting.curl.sh M01).

목록·수정·삭제·열 맞추기·챗봇은 #42 범위다.
"""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.core.enums import RecordCategory
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope
from app.schemas.records import RecordDetailOut, RecordOut
from app.services import record_service

router = APIRouter(prefix="/api/v1/records", tags=["records"])


@router.post("", response_model=Envelope[RecordOut], status_code=201)
async def upload_record(
    club_id: str = Form(..., alias="clubId"),
    category: RecordCategory = Form(RecordCategory.ETC),
    event_id: str | None = Form(None, alias="eventId"),
    file: UploadFile = File(...),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[RecordOut]:
    await ensure_member(session, club_id=club_id, account=account)
    record = await record_service.upload_record(
        session,
        club_id=club_id,
        event_id=event_id,
        category=category,
        file_name=file.filename or "upload",
        content=await file.read(),
    )
    return Envelope(data=RecordOut.model_validate(record))


@router.get("/{record_id}", response_model=Envelope[RecordDetailOut])
async def get_record(
    record_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[RecordDetailOut]:
    record = await record_service.get_record(session, record_id=record_id)
    await ensure_member(session, club_id=record.club_id, account=account)
    return Envelope(data=RecordDetailOut.model_validate(record))
