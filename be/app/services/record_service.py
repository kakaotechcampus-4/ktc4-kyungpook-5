"""동아리 기록 업로드·조회.

업로드한 파일은 요청 안에서 바로 parse_result로 바꾼다(PDF·CSV·XLSX). 실제 작업 큐가
없어서다. 파싱이 성공하면 이어서 app.ai.index_record로 청크를 만들어 저장하고
INDEXED로 바꾼다(#141). 임베딩 호출 중에는 세션을 들고 있지 않는다 — db/session.py의
원칙(#187에서 확인)을 그대로 따른다.
"""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.ai as ai
from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.core.exceptions import ApiError, ValidationFailed
from app.db.session import get_sessionmaker
from app.infra.storage import save_file
from app.models.records import Record, RecordChunk
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

    record = Record(
        club_id=club_id,
        event_id=event_id,
        file_name=file_name,
        file_type=file_type,
        category=category,
        storage_key=save_file(club_id, file_name, content),
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
        await session.close()
        await _index_record(record)
    return record


async def _index_record(record: Record) -> None:
    """파싱된 블록을 청크로 바꿔 저장한다. 실패하면 FAILED("읽지 못함")로 바꾼다."""
    blocks = tuple(
        ai.RecordBlock(
            text=block["text"], location=ai.SourceLocation(label=block["location"]["label"])
        )
        for block in record.parse_result["blocks"]
    )
    request = ai.IndexRecordRequest(
        record_id=record.id, file_name=record.file_name,
        file_type=record.file_type, blocks=blocks,
    )
    try:
        result = await ai.index_record(request)
    except ai.AIEmptyRecordError:
        record.parse_status = RecordParseStatus.FAILED
        record.parse_error = {
            "reason": "UNKNOWN", "params": {}, "debugMessage": "색인할 내용이 없습니다.",
        }
        async with get_sessionmaker()() as session:
            db_record = await session.get(Record, record.id)
            db_record.parse_status = RecordParseStatus.FAILED
            db_record.parse_error = record.parse_error
            await session.commit()
        return

    async with get_sessionmaker()() as session:
        for chunk in result.chunks:
            session.add(
                RecordChunk(
                    record_id=record.id,
                    club_id=record.club_id,
                    file_name=record.file_name,
                    category=record.category,
                    event_id=record.event_id,
                    text=chunk.text,
                    location_label=chunk.location.label,
                    embedding=list(chunk.embedding),
                )
            )
        db_record = await session.get(Record, record.id)
        db_record.parse_status = RecordParseStatus.INDEXED
        await session.commit()
    record.parse_status = RecordParseStatus.INDEXED


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
