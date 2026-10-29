"""소속 권한을 검증한 자료 업로드·목록·조회·색인 재시도."""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.core.enums import RecordCategory
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope, PageMeta
from app.schemas.records import RecordDetailOut, RecordListResponse, RecordOut
from app.services import record_service

router = APIRouter(prefix="/api/v1/records", tags=["records"])


@router.get("", response_model=RecordListResponse)
async def list_records(
    club_id: str = Query(..., alias="clubId"),
    category: RecordCategory | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> RecordListResponse:
    await ensure_member(session, club_id=club_id, account=account)
    rows, total = await record_service.list_records(
        session, club_id=club_id, category=category, page=page, size=size
    )
    return RecordListResponse(
        data=[RecordOut.model_validate(row) for row in rows],
        meta=PageMeta(page=page, size=size, total_count=total),
    )


@router.post("/{record_id}/index", response_model=Envelope[RecordDetailOut])
async def retry_index(
    record_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[RecordDetailOut]:
    record = await record_service.get_record(session, record_id=record_id)
    await ensure_member(session, club_id=record.club_id, account=account)
    record = await record_service.index_record(session, record_id=record_id)
    return Envelope(data=RecordDetailOut.model_validate(record))


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
