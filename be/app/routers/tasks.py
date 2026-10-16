"""할 일 후보 엔드포인트. 실행(execute/send/transfer) 경로는 두지 않는다."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import WRITER_ROLES, require_club_role, require_member
from app.core.enums import ContextSourceType, TaskSuggestionStatus
from app.db.session import get_session
from app.models.clubs import Member
from app.schemas.common import Envelope
from app.schemas.tasks import (
    TaskSuggestionAcceptIn,
    TaskSuggestionOut,
    TaskSuggestionPatchIn,
)
from app.services import task_service

router = APIRouter(prefix="/api/v1/clubs/{club_id}/task-suggestions", tags=["tasks"])


@router.get("", response_model=Envelope[list[TaskSuggestionOut]])
async def list_task_suggestions(
    club_id: str,
    source_type: ContextSourceType | None = Query(None, alias="sourceType"),
    status: TaskSuggestionStatus | None = Query(None),
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[TaskSuggestionOut]]:
    suggestions = await task_service.list_suggestions(
        session, club_id=club_id, source_type=source_type, status=status
    )
    return Envelope(data=[TaskSuggestionOut.model_validate(item) for item in suggestions])


@router.get("/{suggestion_id}", response_model=Envelope[TaskSuggestionOut])
async def get_task_suggestion(
    club_id: str,
    suggestion_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TaskSuggestionOut]:
    suggestion = await task_service.get_suggestion(
        session, club_id=club_id, suggestion_id=suggestion_id
    )
    return Envelope(data=TaskSuggestionOut.model_validate(suggestion))


@router.patch("/{suggestion_id}", response_model=Envelope[TaskSuggestionOut])
async def update_task_suggestion(
    club_id: str,
    suggestion_id: str,
    body: TaskSuggestionPatchIn,
    _member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TaskSuggestionOut]:
    suggestion = await task_service.update_suggestion(
        session, club_id=club_id, suggestion_id=suggestion_id, body=body
    )
    return Envelope(data=TaskSuggestionOut.model_validate(suggestion))


@router.post("/{suggestion_id}/accept", response_model=Envelope[TaskSuggestionOut])
async def accept_task_suggestion(
    club_id: str,
    suggestion_id: str,
    body: TaskSuggestionAcceptIn,
    member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TaskSuggestionOut]:
    suggestion = await task_service.accept_suggestion(
        session,
        club_id=club_id,
        suggestion_id=suggestion_id,
        expected_version=body.expected_version,
        accepted_by=member.id,
    )
    return Envelope(data=TaskSuggestionOut.model_validate(suggestion))
