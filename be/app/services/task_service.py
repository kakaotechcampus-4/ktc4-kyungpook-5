"""할 일 후보 조회·수정·수락.

수락은 상태 기록만 한다. 외부 게시·예약·송금·담당자 연락·완료 처리를 하지 않는다.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ContextSourceType, TaskSuggestionStatus
from app.core.exceptions import ApiError, VersionConflict
from app.models.tasks import TaskSuggestion
from app.schemas.tasks import TaskSuggestionPatchIn


class TaskSuggestionNotFound(ApiError):
    status_code = 404
    code = "TASK_SUGGESTION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 할 일 후보를 찾을 수 없습니다.")


class TaskSuggestionNotProposed(ApiError):
    """이미 수락한 후보를 다시 고치거나 수락하려 할 때."""

    status_code = 409
    code = "TASK_SUGGESTION_NOT_PROPOSED"

    def __init__(self) -> None:
        super().__init__("검토 중인 할 일 후보만 바꿀 수 있습니다.")


async def list_suggestions(
    session: AsyncSession,
    *,
    club_id: str,
    source_type: ContextSourceType | None,
    status: TaskSuggestionStatus | None,
) -> list[TaskSuggestion]:
    query = select(TaskSuggestion).where(TaskSuggestion.club_id == club_id)
    if source_type is not None:
        query = query.where(TaskSuggestion.source_type == source_type)
    if status is not None:
        query = query.where(TaskSuggestion.status == status)
    return list(await session.scalars(query.order_by(TaskSuggestion.created_at.desc())))


async def get_suggestion(
    session: AsyncSession, *, club_id: str, suggestion_id: str
) -> TaskSuggestion:
    suggestion = await session.get(TaskSuggestion, suggestion_id)
    if suggestion is None or suggestion.club_id != club_id:
        raise TaskSuggestionNotFound()
    return suggestion


async def _get_proposed(
    session: AsyncSession, *, club_id: str, suggestion_id: str, expected_version: int
) -> TaskSuggestion:
    suggestion = await get_suggestion(session, club_id=club_id, suggestion_id=suggestion_id)
    if suggestion.version != expected_version:
        raise VersionConflict()
    if suggestion.status != TaskSuggestionStatus.PROPOSED:
        raise TaskSuggestionNotProposed()
    return suggestion


async def update_suggestion(
    session: AsyncSession, *, club_id: str, suggestion_id: str, body: TaskSuggestionPatchIn
) -> TaskSuggestion:
    suggestion = await _get_proposed(
        session,
        club_id=club_id,
        suggestion_id=suggestion_id,
        expected_version=body.expected_version,
    )
    for field in body.model_fields_set - {"expected_version"}:
        setattr(suggestion, field, getattr(body, field))
    suggestion.version += 1
    await session.commit()
    await session.refresh(suggestion)
    return suggestion


async def accept_suggestion(
    session: AsyncSession,
    *,
    club_id: str,
    suggestion_id: str,
    expected_version: int,
    accepted_by: str,
) -> TaskSuggestion:
    suggestion = await _get_proposed(
        session,
        club_id=club_id,
        suggestion_id=suggestion_id,
        expected_version=expected_version,
    )
    suggestion.status = TaskSuggestionStatus.ACCEPTED
    suggestion.accepted_by = accepted_by
    suggestion.accepted_at = datetime.now(UTC)
    suggestion.version += 1
    await session.commit()
    await session.refresh(suggestion)
    return suggestion
