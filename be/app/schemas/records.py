"""동아리 기록 요청·응답 스키마 (FE API 명세 v1 §4)."""

from typing import Any

from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.schemas.common import CamelModel, PageMeta, UtcDateTime


class RecordOut(CamelModel):
    id: str
    file_name: str
    file_type: RecordFileType
    category: RecordCategory
    size: int
    parse_status: RecordParseStatus
    created_at: UtcDateTime


class RecordDetailOut(RecordOut):
    parse_result: dict[str, Any] | None
    # {reason, params, debugMessage}. 화면 문구는 FE가 reason으로 고른다.
    parse_error: dict[str, Any] | None


class RecordListResponse(CamelModel):
    data: list[RecordOut]
    meta: PageMeta
