"""소속 권한을 검증한 자료 업로드·목록·조회·색인 재시도·삭제."""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from urllib.parse import quote
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.core.enums import RecordCategory
from app.core.exceptions import ValidationFailed
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope, PageMeta
from app.schemas.records import RecordDetailOut, RecordListResponse, RecordOut, RecordSearchResponse
from app.services import record_service, record_discovery_service
from app.infra.storage import read_file

router = APIRouter(prefix="/api/v1/records", tags=["records"])


@router.get("/search", response_model=RecordSearchResponse)
async def search_records(
    club_id: str = Query(..., alias="clubId"),
    query: str = Query(..., min_length=1, max_length=200),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> RecordSearchResponse:
    query = query.strip()
    if not query:
        raise ValidationFailed({"query": "검색어를 입력해 주세요."})
    await ensure_member(session, club_id=club_id, account=account)
    data, total = await record_discovery_service.search_records(
        session, club_id=club_id, query=query, page=page, size=size
    )
    return RecordSearchResponse(data=data, meta=PageMeta(page=page, size=size, total_count=total))


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


@router.get("/{record_id}/file")
async def download_record_file(
    record_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Response:
    record = await record_service.get_record(session, record_id=record_id)
    await ensure_member(session, club_id=record.club_id, account=account)
    content = await run_in_threadpool(read_file, record.storage_key)
    return Response(content, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.file_name, safe='')}"
    })


@router.delete("/{record_id}", status_code=204)
async def delete_record(
    record_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Response:
    record = await record_service.get_record(session, record_id=record_id)
    await ensure_member(session, club_id=record.club_id, account=account)
    await record_service.delete_record(session, record_id=record_id)
    return Response(status_code=204)
