"""할 일 후보 요청·응답 스키마."""

from datetime import date
from typing import Any

from pydantic import Field

from app.core.enums import ContextSourceType, TaskSuggestionStatus
from app.schemas.common import CamelModel, UtcDateTime


class TaskSuggestionOut(CamelModel):
    id: str
    decision_id: str
    source_type: ContextSourceType
    title: str
    description: str | None
    suggested_assignee: str | None
    due_date: date | None
    kind: str | None = None
    due_at: UtcDateTime | None = None
    scheduled_at: UtcDateTime | None = None
    unresolved_fields: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]]
    status: TaskSuggestionStatus
    version: int
    accepted_by: str | None
    accepted_at: UtcDateTime | None
    created_at: UtcDateTime


class TaskSuggestionPatchIn(CamelModel):
    """보낸 필드만 바꾼다."""

    expected_version: int
    title: str | None = None
    description: str | None = None
    suggested_assignee: str | None = None
    due_date: date | None = None


class TaskSuggestionAcceptIn(CamelModel):
    expected_version: int
