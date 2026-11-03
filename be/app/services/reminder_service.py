"""사용자 확인으로 항목과 예약을 함께 저장한다. 발송은 push_service 책임이다."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    SERVICE_ROLES, ContextDecisionStatus, ContextSourceType, MemberStatus, TaskSuggestionStatus,
)
from app.core.exceptions import ApiError, IdempotencyConflict, ValidationFailed, VersionConflict
from app.models.agent import ContextDecision
from app.models.clubs import Member
from app.models.meetings import TranscriptSegment
from app.models.reminders import ConfirmedTask, TaskReminder
from app.models.tasks import TaskSuggestion
from app.schemas.reminders import (
    ConfirmedFields,
    ConfirmedTaskUpdateIn,
    ReminderRecipientOut,
    TaskSuggestionConfirmIn,
)
from app.services.task_service import TaskSuggestionNotFound, TaskSuggestionNotProposed


class TaskSuggestionStale(ApiError):
    status_code = 409
    code = "TASK_SUGGESTION_STALE"

    def __init__(self) -> None:
        super().__init__("근거 전사가 바뀐 후보입니다. 최신 후보를 확인해 주세요.")


class ConfirmedTaskNotFound(ApiError):
    status_code = 404
    code = "CONFIRMED_TASK_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 확정 항목을 찾을 수 없습니다.")


class ReminderDispatchInProgress(ApiError):
    status_code = 409
    code = "REMINDER_DISPATCH_IN_PROGRESS"

    def __init__(self) -> None:
        super().__init__("알림 발송을 처리 중입니다. 상태를 확인한 뒤 다시 시도해 주세요.")


class ConfirmedTaskCancelled(ApiError):
    status_code = 409
    code = "CONFIRMED_TASK_CANCELLED"

    def __init__(self) -> None:
        super().__init__("취소한 항목은 변경할 수 없습니다.")


async def list_recipients(session: AsyncSession, *, club_id: str) -> list[ReminderRecipientOut]:
    members = await session.scalars(
        select(Member).where(
            Member.club_id == club_id,
            Member.status == MemberStatus.ACTIVE,
            Member.role.in_(SERVICE_ROLES),
            Member.account_id.is_not(None),
        ).order_by(Member.name, Member.id)
    )
    return [
        ReminderRecipientOut(
            account_id=member.account_id, member_id=member.id, name=member.name, role=member.role
        )
        for member in members
    ]


async def _validate_confirmation(
    session: AsyncSession, *, club_id: str, body: ConfirmedFields
) -> None:
    now = datetime.now(UTC)
    errors: dict[str, str] = {}
    item_at = body.due_at if body.kind == "TASK" else body.scheduled_at
    if item_at is not None and item_at <= now:
        errors["dueAt" if body.kind == "TASK" else "scheduledAt"] = "미래 시각을 선택해 주세요."
    if body.reminder_at <= now:
        errors["reminderAt"] = "미래의 알림 시각을 선택해 주세요."
    account_ids = set(body.recipient_account_ids)
    if body.assignee_account_id is not None:
        account_ids.add(body.assignee_account_id)
    valid = set(await session.scalars(select(Member.account_id).where(
        Member.club_id == club_id,
        Member.status == MemberStatus.ACTIVE,
        Member.role.in_(SERVICE_ROLES),
        Member.account_id.in_(account_ids),
    )))
    if not set(body.recipient_account_ids).issubset(valid):
        errors["recipientAccountIds"] = "현재 소속의 활성 회장·임원 계정만 수신자로 선택할 수 있습니다."
    if body.assignee_account_id is not None and body.assignee_account_id not in valid:
        errors["assigneeAccountId"] = "현재 소속의 활성 회장·임원 계정만 담당자로 선택할 수 있습니다."
    if errors:
        raise ValidationFailed(errors)


def _confirmation_hash(body: TaskSuggestionConfirmIn) -> str:
    payload = body.model_dump(mode="json", exclude={"expected_version"})
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def list_confirmed_tasks(
    session: AsyncSession, *, club_id: str, suggestion_id: str | None = None,
    meeting_id: str | None = None,
) -> list[ConfirmedTask]:
    query = select(ConfirmedTask).where(ConfirmedTask.club_id == club_id)
    if meeting_id is not None:
        query = query.join(TaskSuggestion, ConfirmedTask.suggestion_id == TaskSuggestion.id).join(
            ContextDecision, TaskSuggestion.decision_id == ContextDecision.id
        ).where(ContextDecision.club_id == club_id, ContextDecision.meeting_id == meeting_id)
    if suggestion_id is not None:
        query = query.where(ConfirmedTask.suggestion_id == suggestion_id)
    return list(await session.scalars(query.order_by(ConfirmedTask.created_at.desc())))


async def get_confirmed_task(
    session: AsyncSession, *, club_id: str, item_id: str, lock: bool = False
) -> ConfirmedTask:
    query = select(ConfirmedTask).where(
        ConfirmedTask.id == item_id, ConfirmedTask.club_id == club_id
    ).options(selectinload(ConfirmedTask.reminder))
    if lock:
        query = query.with_for_update()
    item = await session.scalar(query)
    if item is None:
        raise ConfirmedTaskNotFound()
    return item


async def _assert_current_source(session: AsyncSession, suggestion: TaskSuggestion) -> None:
    decision = await session.get(ContextDecision, suggestion.decision_id)
    if decision is None or decision.club_id != suggestion.club_id:
        raise TaskSuggestionStale()
    # 전사 정정 경로와 같은 segment -> decision 순서로 잠근다.
    if suggestion.source_type == ContextSourceType.MEETING_TRANSCRIPT:
        sources = decision.sources
        source_ids = [source.get("sourceId") for source in sources]
        if not source_ids or any(not isinstance(source_id, str) for source_id in source_ids):
            raise TaskSuggestionStale()
        segments = {segment.id: segment for segment in await session.scalars(
            select(TranscriptSegment).where(TranscriptSegment.id.in_(source_ids))
            .order_by(TranscriptSegment.id).with_for_update()
            .execution_options(populate_existing=True)
        )}
        for source in sources:
            segment = segments.get(source["sourceId"])
            if (segment is None or segment.meeting_id != decision.meeting_id
                    or segment.version != source.get("sourceVersion")):
                raise TaskSuggestionStale()
    current = await session.scalar(select(ContextDecision).where(
        ContextDecision.id == suggestion.decision_id
    ).with_for_update().execution_options(populate_existing=True))
    if current is None or current.status == ContextDecisionStatus.STALE:
        raise TaskSuggestionStale()


async def confirm_suggestion(
    session: AsyncSession,
    *,
    club_id: str,
    suggestion_id: str,
    confirmed_by: str,
    body: TaskSuggestionConfirmIn,
) -> ConfirmedTask:
    # 한 후보에 대한 동시에 들어온 확인을 직렬화한다. DB unique도 중복을 막는다.
    suggestion = await session.scalar(select(TaskSuggestion).where(
        TaskSuggestion.id == suggestion_id, TaskSuggestion.club_id == club_id
    ).with_for_update())
    if suggestion is None:
        raise TaskSuggestionNotFound()
    fingerprint = _confirmation_hash(body)
    existing = await session.scalar(select(ConfirmedTask).where(
        ConfirmedTask.suggestion_id == suggestion_id
    ))
    if existing is not None:
        if existing.source_version != body.expected_version or existing.confirmation_hash != fingerprint:
            raise IdempotencyConflict()
        return existing
    if suggestion.version != body.expected_version:
        raise VersionConflict()
    # 이전 /accept는 수락 기록뿐이다. 그 후보도 별도 확인을 거쳐 예약할 수 있다.
    if suggestion.status not in (TaskSuggestionStatus.PROPOSED, TaskSuggestionStatus.ACCEPTED):
        raise TaskSuggestionNotProposed()
    await _assert_current_source(session, suggestion)
    await _validate_confirmation(session, club_id=club_id, body=body)
    values = body.model_dump(exclude={"expected_version", "reminder_at", "recipient_account_ids"})
    item = ConfirmedTask(
        club_id=club_id, suggestion_id=suggestion.id, source_version=body.expected_version,
        confirmation_hash=fingerprint, confirmed_by=confirmed_by, **values,
    )
    item.reminder = TaskReminder(
        club_id=club_id, reminder_at=body.reminder_at,
        recipient_account_ids=body.recipient_account_ids,
    )
    session.add(item)
    if suggestion.status == TaskSuggestionStatus.PROPOSED:
        suggestion.status = TaskSuggestionStatus.ACCEPTED
        suggestion.accepted_by = confirmed_by
        suggestion.accepted_at = datetime.now(UTC)
        suggestion.version += 1
    await session.commit()
    await session.refresh(item)
    return item


async def _editable_item(
    session: AsyncSession, *, club_id: str, item_id: str, expected_version: int
) -> tuple[ConfirmedTask, TaskReminder]:
    item = await get_confirmed_task(session, club_id=club_id, item_id=item_id, lock=True)
    if item.version != expected_version:
        raise VersionConflict()
    reminder = await session.scalar(select(TaskReminder).where(
        TaskReminder.confirmed_item_id == item.id
    ).with_for_update().execution_options(populate_existing=True))
    assert reminder is not None  # 항목과 예약은 같은 트랜잭션에서 생성한다.
    if reminder.status == "SENDING":
        raise ReminderDispatchInProgress()
    return item, reminder


async def update_confirmed_task(
    session: AsyncSession, *, club_id: str, item_id: str, body: ConfirmedTaskUpdateIn
) -> ConfirmedTask:
    item, reminder = await _editable_item(
        session, club_id=club_id, item_id=item_id, expected_version=body.expected_version
    )
    if item.status == "CANCELLED":
        raise ConfirmedTaskCancelled()
    await _validate_confirmation(session, club_id=club_id, body=body)
    for field, value in body.model_dump(exclude={
        "expected_version", "reminder_at", "recipient_account_ids"
    }).items():
        setattr(item, field, value)
    item.version += 1
    reminder.reminder_at = body.reminder_at
    reminder.recipient_account_ids = body.recipient_account_ids
    reminder.status = "PENDING"
    reminder.attempted_at = None
    reminder.last_error = None
    reminder.accepted_count = 0
    reminder.failed_count = 0
    reminder.version += 1
    await session.commit()
    await session.refresh(item)
    return item


async def cancel_confirmed_task(
    session: AsyncSession, *, club_id: str, item_id: str, expected_version: int
) -> ConfirmedTask:
    item, reminder = await _editable_item(
        session, club_id=club_id, item_id=item_id, expected_version=expected_version
    )
    if item.status != "CANCELLED":
        item.status = "CANCELLED"
        item.version += 1
        # 이미 서비스가 접수한 Push는 회수하지 못한다. 발송 결과는 보존한다.
        if reminder.status == "PENDING":
            reminder.status = "CANCELLED"
            reminder.version += 1
        await session.commit()
        await session.refresh(item)
    return item
