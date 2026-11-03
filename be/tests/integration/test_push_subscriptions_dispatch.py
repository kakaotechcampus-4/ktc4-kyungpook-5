"""실제 PostgreSQL에 계정 구독·발송 결과·지정 수신자 예약을 저장한다.

Push 네트워크 경계만 대체하므로 실제 기기 수신을 검증한 테스트는 아니다.
"""

import base64
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.enums import (
    AgentJobKind, ContextDecisionStatus, ContextSourceType, JudgeKind, JudgeRoute,
    MemberRole, MemberStatus,
)
from app.db import session as db_session
from app.db.base import new_id
from app.infra.web_push import PushResult
from app.models.agent import AgentJob, ContextDecision
from app.models.auth import Account
from app.models.clubs import Club, Member
from app.models.reminders import ConfirmedTask, TaskReminder
from app.models.tasks import TaskSuggestion
from app.schemas.push import PushSubscriptionIn
from app.services import push_service

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None,
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _subscription() -> dict:
    def b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")
    return {
        "endpoint": f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4().hex}",
        "keys": {"p256dh": b64(b"\x04" + b"x" * 64), "auth": b64(b"a" * 16)},
        "expirationTime": None,
    }


def _login(client: TestClient, *, service_membership: bool = True) -> tuple[dict, str]:
    email = f"push-{uuid.uuid4().hex}@example.com"
    signup = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "PmTest-2027!", "name": "Push tester",
    })
    assert signup.status_code == 201, signup.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "PmTest-2027!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}
    if service_membership:
        club = client.post("/api/v1/clubs", headers=headers, json={"name": "Push 운영팀"})
        assert club.status_code == 201, club.text
    return headers, signup.json()["data"]["id"]


async def test_subscription_ownership_deduplication_and_private_keys_not_returned(client, app_db) -> None:
    owner, _ = _login(client)
    other, _ = _login(client)
    body = _subscription()
    saved = client.post("/api/v1/push/subscriptions", headers=owner, json=body)
    assert saved.status_code == 201, saved.text
    data = saved.json()["data"]
    assert data["active"] is True
    assert "endpoint" not in data and "keys" not in data and "auth" not in data
    subscription_id = data["id"]
    again = client.post("/api/v1/push/subscriptions", headers=owner, json=body)
    assert again.json()["data"]["id"] == subscription_id
    assert len(client.get("/api/v1/push/subscriptions", headers=owner).json()["data"]) == 1
    assert client.get("/api/v1/push/subscriptions", headers=other).json()["data"] == []
    conflict = client.post("/api/v1/push/subscriptions", headers=other, json=body)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PUSH_SUBSCRIPTION_CONFLICT"
    assert client.delete(f"/api/v1/push/subscriptions/{subscription_id}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/push/subscriptions/{subscription_id}", headers=owner).status_code == 200


async def test_ordinary_member_cannot_use_push_endpoints(client, app_db) -> None:
    headers, account_id = _login(client, service_membership=False)
    async with db_session.get_sessionmaker()() as session:
        club = Club(name="일반 동아리원 명단")
        session.add(club)
        await session.flush()
        session.add(Member(club_id=club.id, account_id=account_id, name="일반 동아리원",
                           role=MemberRole.MEMBER, status=MemberStatus.ACTIVE))
        await session.commit()
    calls = (
        ("get", "/api/v1/push/vapid-public-key", None),
        ("get", "/api/v1/push/subscriptions", None),
        ("post", "/api/v1/push/subscriptions", _subscription()),
        ("delete", "/api/v1/push/subscriptions/sub_missing", None),
        ("post", "/api/v1/push/test", {}),
    )
    for method, url, body in calls:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        response = client.request(method, url, **kwargs)
        assert response.status_code == 403, response.text


class RecordingTransport:
    def __init__(self, result: PushResult = PushResult(True)) -> None:
        self.result = result
        self.calls = []

    async def send(self, target, payload):
        self.calls.append((target, payload))
        return self.result


async def test_test_push_only_targets_current_account_and_invalidates_gone_subscription(client, app_db) -> None:
    _, account_id = _login(client)
    _, other_id = _login(client)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        own = await push_service.register_subscription(
            session, account_id=account_id, body=PushSubscriptionIn.model_validate(_subscription())
        )
        other = await push_service.register_subscription(
            session, account_id=other_id, body=PushSubscriptionIn.model_validate(_subscription())
        )
        transport = RecordingTransport(PushResult(False, "PUSH_HTTP_410", True))
        result = await push_service.test_push(
            session, account_id=account_id, subscription_id=None, transport=transport,
        )
        assert result.status == "FAILED" and result.accepted_count == 0
        assert result.failed_count == 1 and result.invalidated_count == 1
        assert [target.id for target, _ in transport.calls] == [own.id]
        await session.refresh(own)
        await session.refresh(other)
        assert own.active is False and own.last_error == "PUSH_HTTP_410"
        assert other.active is True


async def _due_reminder_fixture(session) -> tuple[str, str, str, str]:
    active, unavailable, unselected, ordinary = [new_id("acc") for _ in range(4)]
    club_id, member_id, job_id, decision_id, suggestion_id, item_id = [
        new_id(prefix) for prefix in ("clb", "mbr", "job", "cdc", "tsk", "ctk")
    ]
    session.add_all([Account(id=account_id, email=f"{account_id}@example.com")
                     for account_id in (active, unavailable, unselected, ordinary)])
    session.add(Club(id=club_id, name="Push due test"))
    await session.flush()
    session.add_all([
        Member(id=member_id, club_id=club_id, account_id=active, name="지정 수신자", role=MemberRole.OWNER, status=MemberStatus.ACTIVE),
        Member(club_id=club_id, account_id=unavailable, name="가입 미승인", role=MemberRole.MANAGER, status=MemberStatus.PENDING),
        Member(club_id=club_id, account_id=unselected, name="지정 안 함", role=MemberRole.MANAGER, status=MemberStatus.ACTIVE),
        Member(club_id=club_id, account_id=ordinary, name="일반 동아리원", role=MemberRole.MEMBER, status=MemberStatus.ACTIVE),
    ])
    session.add(AgentJob(id=job_id, club_id=club_id, kind=AgentJobKind.CONTEXT_DECISION))
    await session.flush()
    session.add(ContextDecision(
        id=decision_id, club_id=club_id, job_id=job_id,
        source_type=ContextSourceType.MEETING_TRANSCRIPT, sources=[],
        status=ContextDecisionStatus.SUCCEEDED, route=JudgeRoute.NONE,
        kind=JudgeKind.NO_LOOKUP, tool_calls=[], model_version="fixture", policy_version="fixture",
    ))
    await session.flush()
    session.add(TaskSuggestion(id=suggestion_id, club_id=club_id, decision_id=decision_id,
                               source_type=ContextSourceType.MEETING_TRANSCRIPT, title="회의 자료 준비", evidence=[]))
    await session.flush()
    session.add(ConfirmedTask(
        id=item_id, club_id=club_id, suggestion_id=suggestion_id, source_version=1,
        confirmation_hash="a" * 64, kind="TASK", title="회의 자료 준비", timezone="Asia/Seoul",
        confirmed_by=member_id,
    ))
    await session.flush()
    reminder = TaskReminder(club_id=club_id, confirmed_item_id=item_id,
                            reminder_at=datetime.now(UTC) - timedelta(seconds=2),
                            recipient_account_ids=[active, unavailable, ordinary])
    session.add(reminder)
    await session.commit()
    subscriptions = []
    for account_id in (active, unavailable, unselected, ordinary):
        subscriptions.append(await push_service.register_subscription(
            session, account_id=account_id, body=PushSubscriptionIn.model_validate(_subscription())
        ))
    return reminder.id, subscriptions[0].id, subscriptions[1].id, subscriptions[3].id


async def test_due_reminder_sends_once_and_rechecks_membership_and_designation(app_db) -> None:
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        reminder_id, selected_subscription, unavailable_subscription, ordinary_subscription = await _due_reminder_fixture(session)
    transport = RecordingTransport()
    processed = await push_service.dispatch_due_reminders(session_factory=factory, transport=transport)
    assert processed >= 1
    assert [target.id for target, _ in transport.calls] == [selected_subscription]
    assert unavailable_subscription not in [target.id for target, _ in transport.calls]
    assert ordinary_subscription not in [target.id for target, _ in transport.calls]
    payload = transport.calls[0][1]
    assert payload["type"] == "TASK_REMINDER"
    assert payload["data"]["reminderId"] == reminder_id
    async with factory() as session:
        reminder = await session.get(TaskReminder, reminder_id)
        assert reminder.status == "SERVICE_ACCEPTED"
        assert reminder.accepted_count == 1 and reminder.failed_count == 2
        assert reminder.attempted_at is not None
        assert reminder.last_error == "RECIPIENT_UNAVAILABLE_OR_UNSUBSCRIBED"
    await push_service.dispatch_due_reminders(session_factory=factory, transport=transport)
    assert len(transport.calls) == 1


async def test_due_reminder_rechecks_role_changed_after_confirmation(app_db) -> None:
    from sqlalchemy import select
    from app.models.push import PushSubscription

    factory = db_session.get_sessionmaker()
    async with factory() as session:
        reminder_id, selected_subscription, _, _ = await _due_reminder_fixture(session)
        subscription = await session.get(PushSubscription, selected_subscription)
        member = await session.scalar(select(Member).where(Member.account_id == subscription.account_id))
        member.role = MemberRole.MEMBER
        await session.commit()
    transport = RecordingTransport()
    await push_service.dispatch_due_reminders(session_factory=factory, transport=transport)
    assert transport.calls == []
    async with factory() as session:
        reminder = await session.get(TaskReminder, reminder_id)
        assert reminder.status == "FAILED"
        assert reminder.accepted_count == 0 and reminder.failed_count == 3
        assert reminder.last_error == "RECIPIENT_UNAVAILABLE_OR_UNSUBSCRIBED"


async def test_explicit_push_test_missing_configuration_is_503(client, app_db, monkeypatch) -> None:
    headers, _ = _login(client)
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC_KEY", "")
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE_KEY", "")
    monkeypatch.setenv("WEB_PUSH_VAPID_SUBJECT", "")
    from app.core.config import get_settings
    get_settings.cache_clear()
    response = client.post("/api/v1/push/test", headers=headers, json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PUSH_NOT_CONFIGURED"
