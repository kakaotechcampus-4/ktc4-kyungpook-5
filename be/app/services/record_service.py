"""동아리 기록 업로드·조회.

업로드 요청에서 PDF·CSV·XLSX를 파싱한 뒤 공개 index_record로 청크를 만들어 저장한다.
파싱 성공(COMPLETED), 검색 준비 성공(INDEXED), 색인 실패(index_error)를 구분한다.
"""

import math
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app import ai

from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.core.exceptions import ApiError, ValidationFailed
from app.infra.storage import save_file
from app.models.records import Record
from app.models.record_chunks import RecordChunk
from app.models.events import Event
from app.services.record_parser import RecordParseError, parse_record

_FILE_TYPES = {
    ".csv": RecordFileType.CSV,
    ".pdf": RecordFileType.PDF,
    ".xlsx": RecordFileType.XLSX,
    ".hwp": RecordFileType.HWP,
    ".jpg": RecordFileType.IMAGE,
    ".jpeg": RecordFileType.IMAGE,
    ".png": RecordFileType.IMAGE,
}


class RecordNotFound(ApiError):
    status_code = 404
    code = "RECORD_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 기록을 찾을 수 없습니다.")


async def upload_record(
    session: AsyncSession,
    *,
    club_id: str,
    event_id: str | None,
    category: RecordCategory,
    file_name: str,
    content: bytes,
) -> Record:
    file_type = _FILE_TYPES.get(Path(file_name).suffix.lower())
    if file_type is None:
        raise ValidationFailed({"file": "지원하지 않는 파일 형식입니다."})
    if event_id is not None:
        event = await session.get(Event, event_id)
        if event is None or event.club_id != club_id:
            raise ValidationFailed({"eventId": "같은 조직의 행사만 연결할 수 있습니다."})

    record = Record(
        club_id=club_id,
        event_id=event_id,
        file_name=file_name,
        file_type=file_type,
        category=category,
        storage_key=await run_in_threadpool(save_file, club_id, file_name, content),
        size=len(content),
        parse_status=RecordParseStatus.PARSING,
    )
    try:
        record.parse_result = parse_record(content, file_type)
        record.parse_status = RecordParseStatus.COMPLETED
    except RecordParseError as error:
        record.parse_status = RecordParseStatus.FAILED
        record.parse_error = {
            "reason": error.reason.value,
            "params": error.params,
            "debugMessage": error.debug_message,
        }
    session.add(record)
    await session.commit()
    await session.refresh(record)
    if record.parse_status == RecordParseStatus.COMPLETED:
        return await index_record(session, record_id=record.id)
    return record


async def index_record(session: AsyncSession, *, record_id: str) -> Record:
    record = await get_record(session, record_id=record_id)
    if record.parse_status == RecordParseStatus.INDEXED:
        return record
    if record.parse_status != RecordParseStatus.COMPLETED:
        raise ValidationFailed({"recordId": "파싱이 완료된 자료만 색인할 수 있습니다."})
    request = ai.IndexRecordRequest(
        record_id=record.id, file_name=record.file_name, file_type=record.file_type,
        blocks=tuple(ai.RecordBlock.model_validate(block) for block in (record.parse_result or {}).get("blocks", [])),
    )
    # 모델 호출 동안 DB 트랜잭션/연결을 점유하지 않는다.
    await session.commit()
    try:
        result = await ai.index_record(request)
        if any(not all(math.isfinite(value) for value in chunk.embedding) or not any(chunk.embedding) for chunk in result.chunks):
            raise ai.AIInvalidResponseError("임베딩은 유한한 비영 벡터여야 합니다")
    except ai.AIError as error:
        record = await session.get(Record, record_id, populate_existing=True)
        if record.parse_status != RecordParseStatus.INDEXED:
            record.index_error = {"code": type(error).__name__, "message": "검색 준비에 실패했습니다. 설정을 확인하거나 다시 시도해 주세요."}
            await session.commit()
        return record
    record = await session.scalar(select(Record).where(Record.id == record_id).with_for_update().execution_options(populate_existing=True))
    if record.parse_status != RecordParseStatus.INDEXED:
        await session.execute(delete(RecordChunk).where(RecordChunk.record_id == record_id))
        session.add_all([
            RecordChunk(record_id=record.id, chunk_index=index, text=chunk.text,
                        location=chunk.location.model_dump(mode="json"),
                        block_indexes=list(chunk.block_indexes), embedding=list(chunk.embedding))
            for index, chunk in enumerate(result.chunks)
        ])
        record.parse_status = RecordParseStatus.INDEXED
        record.index_error = None
    await session.commit()
    await session.refresh(record)
    return record


async def get_record(session: AsyncSession, *, record_id: str) -> Record:
    record = await session.get(Record, record_id)
    if record is None:
        raise RecordNotFound()
    return record


async def list_records(
    session: AsyncSession,
    *,
    club_id: str,
    category: RecordCategory | None,
    page: int,
    size: int,
) -> tuple[list[Record], int]:
    conditions = [Record.club_id == club_id]
    if category is not None:
        conditions.append(Record.category == category)

    total = await session.scalar(
        select(func.count()).select_from(Record).where(*conditions)
    )
    rows = await session.scalars(
        select(Record)
        .where(*conditions)
        .order_by(Record.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows), total or 0
