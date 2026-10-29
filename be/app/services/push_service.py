"""계정 기기 구독·명시적 테스트 발송·DB의 한 번짜리 예약 실행.

단일 서버 실행기다. Push 서비스가 요청을 접수해도 실제 기기 표시를 확인한 것은
아니다. 발송 중 프로세스가 종료된 SENDING은 자동 재발송하지 않는다(중복 방지).
"""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.enums import SERVICE_ROLES, MemberStatus
from app.core.exceptions import ApiError
from app.db.session import get_sessionmaker
from app.infra.web_push import PushTarget, PushTransport, WebPushTransport
from app.models.clubs import Member
from app.models.push import PushSubscription
from app.schemas.push import PushDispatchOut, PushFailureOut, PushSubscriptionIn

logger = logging.getLogger(__name__)


class PushNotConfigured(ApiError):
    status_code = 503
    code = "PUSH_NOT_CONFIGURED"

    def __init__(self) -> None:
        super().__init__("Web Push 설정이 준비되지 않았습니다.")


class PushSubscriptionNotFound(ApiError):
    status_code = 404
    code = "PUSH_SUBSCRIPTION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("이 계정의 해당 기기 구독을 찾을 수 없습니다.")


class PushSubscriptionConflict(ApiError):
    status_code = 409
    code = "PUSH_SUBSCRIPTION_CONFLICT"

    def __init__(self) -> None:
        super().__init__("다른 계정에 연결된 구독입니다. 기존 계정에서 구독을 해제해 주세요.")


class PushNoSubscription(ApiError):
    status_code = 409
    code = "PUSH_NO_SUBSCRIPTION"

    def __init__(self) -> None:
        super().__init__("활성 기기 구독이 없습니다. 이 브라우저에서 알림을 허용해 주세요.")


def public_key() -> str:
    settings = get_settings()
    if not (
        settings.web_push_vapid_public_key
        and settings.web_push_vapid_private_key.get_secret_value()
        and settings.web_push_vapid_subject
    ):
        raise PushNotConfigured()
    return settings.web_push_vapid_public_key


async def list_subscriptions(session: AsyncSession, *, account_id: str) -> list[PushSubscription]:
    return list(await session.scalars(
        select(PushSubscription).where(PushSubscription.account_id == account_id)
        .order_by(PushSubscription.created_at.desc())
    ))


async def register_subscription(
    session: AsyncSession, *, account_id: str, body: PushSubscriptionIn
) -> PushSubscription:
    endpoint_hash = hashlib.sha256(body.endpoint.encode()).hexdigest()
    item = await session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint_hash == endpoint_hash)
        .with_for_update()
    )
    if item is not None and item.account_id != account_id:
        raise PushSubscriptionConflict()
    if item is None:
        item = PushSubscription(account_id=account_id, endpoint_hash=endpoint_hash)
        session.add(item)
    item.endpoint = body.endpoint
    item.p256dh = body.keys.p256dh
    item.auth = body.keys.auth
    item.expiration_time = (
        datetime.fromtimestamp(body.expiration_time / 1000, UTC)
        if body.expiration_time is not None else None
    )
    item.active = True
    item.last_error = None
    try:
        await session.commit()
    except IntegrityError:
        # 동시 구독 등록도 endpoint 하나가 두 계정으로 연결되지 않게 한다.
        await session.rollback()
        existing = await session.scalar(select(PushSubscription).where(
            PushSubscription.endpoint_hash == endpoint_hash
        ))
        if existing is None or existing.account_id != account_id:
            raise PushSubscriptionConflict() from None
        # 같은 계정의 동시 요청은 마지막으로 저장된 정상 구독을 재사용한다.
        return existing
    await session.refresh(item)
    return item


async def delete_subscription(
    session: AsyncSession, *, account_id: str, subscription_id: str
) -> None:
    item = await session.get(PushSubscription, subscription_id)
    if item is None or item.account_id != account_id:
        raise PushSubscriptionNotFound()
    await session.delete(item)
    await session.commit()


@dataclass
class DispatchSummary:
    accepted_count: int = 0
    failed_count: int = 0
    invalidated_count: int = 0
    failures: list[PushFailureOut] = field(default_factory=list)

    def output(self) -> PushDispatchOut:
        status = "SERVICE_ACCEPTED" if self.accepted_count else "FAILED"
        if self.accepted_count and self.failed_count:
            status = "PARTIAL_FAILURE"
        return PushDispatchOut(
            status=status, accepted_count=self.accepted_count,
            failed_count=self.failed_count, invalidated_count=self.invalidated_count,
            failures=self.failures,
        )


async def _deliver(
    session: AsyncSession, subscriptions: list[PushSubscription],
    payload: dict[str, Any], transport: PushTransport,
) -> DispatchSummary:
    now = datetime.now(UTC)
    targets = [
        (PushTarget(item.id, item.endpoint, item.p256dh, item.auth), item.expiration_time)
        for item in subscriptions
    ]
    # 네트워크를 기다리는 동안 조회 트랜잭션을 열어 두지 않는다.
    await session.commit()
    summary = DispatchSummary()
    for target, expires in targets:
        if expires is not None and expires <= now:
            from app.infra.web_push import PushResult
            result = PushResult(False, "PUSH_SUBSCRIPTION_EXPIRED", True)
        else:
            result = await transport.send(target, payload)
        values: dict[str, Any] = {"last_used_at": datetime.now(UTC), "last_error": result.error_code}
        if result.accepted:
            summary.accepted_count += 1
        else:
            summary.failed_count += 1
            summary.failures.append(PushFailureOut(
                subscription_id=target.id, code=result.error_code or "PUSH_TRANSPORT_FAILED"
            ))
        if result.invalidated:
            values["active"] = False
            summary.invalidated_count += 1
        await session.execute(update(PushSubscription).where(
            PushSubscription.id == target.id
        ).values(**values))
        await session.commit()
    return summary


async def test_push(
    session: AsyncSession, *, account_id: str, subscription_id: str | None,
    transport: PushTransport | None = None,
) -> PushDispatchOut:
    # 설정 누락을 테스트 성공 또는 빈 전송으로 숨기지 않는다.
    if transport is None:
        public_key()
        transport = WebPushTransport()
    query = select(PushSubscription).where(
        PushSubscription.account_id == account_id, PushSubscription.active.is_(True)
    )
    if subscription_id is not None:
        query = query.where(PushSubscription.id == subscription_id)
    subscriptions = list(await session.scalars(query))
    if not subscriptions:
        if subscription_id:
            raise PushSubscriptionNotFound()
        raise PushNoSubscription()
    result = await _deliver(session, subscriptions, {
        "type": "PUSH_TEST", "title": "운영해 테스트 알림",
        "body": "이 기기에서 운영해 알림을 확인했습니다.",
        "tag": "unyounghae-push-test", "data": {"url": "/"}, "url": "/",
    }, transport)
    return result.output()


@dataclass(frozen=True)
class DueReminder:
    id: str
    club_id: str
    confirmed_item_id: str
    recipient_account_ids: list[str]
    title: str
    description: str | None


async def _claim_due(session: AsyncSession, now: datetime) -> DueReminder | None:
    from app.models.reminders import ConfirmedTask, TaskReminder
    # 하나의 서버 실행기만 사용한다. row lock은 API 변경·취소와의 경쟁만 막는다.
    reminder = await session.scalar(
        select(TaskReminder).where(
            TaskReminder.status == "PENDING", TaskReminder.reminder_at <= now
        ).order_by(TaskReminder.reminder_at).limit(1).with_for_update(skip_locked=True)
    )
    if reminder is None:
        await session.rollback()
        return None
    item = await session.get(ConfirmedTask, reminder.confirmed_item_id)
    if item is None or item.status != "ACTIVE":
        reminder.status = "CANCELLED"
        reminder.version += 1
        await session.commit()
        return None
    reminder.status = "SENDING"
    reminder.attempted_at = now
    reminder.version += 1
    claimed = DueReminder(
        reminder.id, reminder.club_id, reminder.confirmed_item_id,
        list(reminder.recipient_account_ids), item.title, item.description,
    )
    await session.commit()
    return claimed


async def _dispatch_claimed(
    session: AsyncSession, due: DueReminder, transport: PushTransport,
) -> None:
    from app.models.reminders import TaskReminder
    # 예약 후 탈퇴/비활성화되거나 회장·임원에서 제외된 계정은 보내지 않는다.
    active_accounts = set(await session.scalars(select(Member.account_id).where(
        Member.club_id == due.club_id, Member.status == MemberStatus.ACTIVE,
        Member.role.in_(SERVICE_ROLES),
        Member.account_id.in_(due.recipient_account_ids),
    )))
    subscriptions = list(await session.scalars(select(PushSubscription).where(
        PushSubscription.account_id.in_(active_accounts), PushSubscription.active.is_(True)
    )))
    subscribed_accounts = {item.account_id for item in subscriptions}
    missing_count = len(set(due.recipient_account_ids) - subscribed_accounts)
    url = "/meetings?" + urlencode({"taskId": due.confirmed_item_id, "clubId": due.club_id})
    summary = await _deliver(session, subscriptions, {
        "type": "TASK_REMINDER", "title": due.title,
        "body": (due.description or due.title)[:500], "tag": f"reminder:{due.id}",
        "url": url, "data": {"url": url, "clubId": due.club_id,
        "confirmedItemId": due.confirmed_item_id, "reminderId": due.id},
    }, transport)
    failed = summary.failed_count + missing_count
    errors = sorted({failure.code for failure in summary.failures})
    if missing_count:
        errors.append("RECIPIENT_UNAVAILABLE_OR_UNSUBSCRIBED")
    await session.execute(update(TaskReminder).where(
        TaskReminder.id == due.id, TaskReminder.status == "SENDING"
    ).values(
        status="SERVICE_ACCEPTED" if summary.accepted_count else "FAILED",
        accepted_count=summary.accepted_count, failed_count=failed,
        last_error=",".join(errors) or None,
        version=TaskReminder.version + 1,
    ))
    await session.commit()


async def dispatch_due_reminders(
    *, session_factory: async_sessionmaker[AsyncSession] | None = None,
    transport: PushTransport | None = None, limit: int = 25,
) -> int:
    """현재 시각까지의 예약을 최대 limit개 시도. 호출마다 새 DB 조회를 한다."""
    factory = session_factory or get_sessionmaker()
    sender = transport or WebPushTransport()
    processed = 0
    for _ in range(limit):
        async with factory() as session:
            due = await _claim_due(session, datetime.now(UTC))
            if due is None:
                break
            try:
                await _dispatch_claimed(session, due, sender)
            except Exception as exc:
                await session.rollback()
                # 외부 서비스 오류 원문·구독·키를 저장하지 않는다.
                from app.models.reminders import TaskReminder
                await session.execute(update(TaskReminder).where(
                    TaskReminder.id == due.id, TaskReminder.status == "SENDING"
                ).values(last_error="PUSH_DISPATCH_RESULT_UNCERTAIN",
                         version=TaskReminder.version + 1))
                await session.commit()
                logger.warning("Reminder dispatch failed (%s)", type(exc).__name__)
            processed += 1
    return processed


async def run_reminder_dispatcher(stop_event: asyncio.Event) -> None:
    """한 서버 프로세스에서 켜는 작은 DB poller. 종료 신호는 sleep을 즉시 깨운다."""
    while not stop_event.is_set():
        try:
            await dispatch_due_reminders()
        except Exception as exc:
            logger.warning("Reminder poll failed (%s)", type(exc).__name__)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=get_settings().reminder_poll_seconds)
        except TimeoutError:
            pass
