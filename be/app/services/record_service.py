"""동아리 기록 업로드·조회.

업로드한 파일은 요청 안에서 바로 parse_result로 바꾼다(PDF·CSV·XLSX). 실제 작업 큐가
없어서다. AI 색인(index_record → INDEXED)은 청크 저장소가 아직 없어 하지 않는다 —
성공해도 COMPLETED까지만 간다.
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.core.exceptions import ApiError, ValidationFailed
from app.infra.storage import save_file
from app.models.records import Record
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
    return record


async def get_record(session: AsyncSession, *, record_id: str) -> Record:
    record = await session.get(Record, record_id)
    if record is None:
        raise RecordNotFound()
    return record
