"""DB 확인·중복 방지·소속 수신자·예약 변경/취소. 제품 test-support는 쓰지 않는다."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.enums import (
    AgentJobKind, AgentJobStatus, ContextDecisionStatus, ContextSourceType,
    JudgeKind, JudgeRoute, MemberRole, MemberStatus,
)
from app.core.security import hash_token
from app.db import session as db_session
from app.models.agent import AgentJob, ContextDecision
from app.models.auth import Account, Auth
from app.models.clubs import Club, Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.reminders import ConfirmedTask, TaskReminder
from app.models.tasks import TaskSuggestion
from app.schemas.reminders import TaskSuggestionConfirmIn
from app.services.reminder_service import confirm_suggestion

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


@pytest.fixture
async def case(app_db: None) -> AsyncIterator[dict]:
    tag = uuid.uuid4().hex
    accounts = [Account(email=f"confirmed-{tag}-{i}@example.com") for i in range(5)]
    clubs = [Club(name=f"confirmed-{tag}"), Club(name=f"outsider-{tag}")]
    tokens = [f"confirmed-test-{tag}-{i}" for i in range(5)]
    async with db_session.get_sessionmaker()() as session:
        session.add_all(accounts + clubs)
        await session.flush()
        session.add_all([
            Member(club_id=clubs[0].id, account_id=accounts[0].id, name="대표", role=MemberRole.OWNER),
            Member(club_id=clubs[0].id, account_id=accounts[1].id, name="운영진", role=MemberRole.MANAGER),
            Member(club_id=clubs[0].id, account_id=accounts[2].id, name="회원", role=MemberRole.MEMBER),
            Member(club_id=clubs[0].id, account_id=accounts[3].id, name="가입 대기", role=MemberRole.MEMBER, status=MemberStatus.PENDING),
            Member(club_id=clubs[1].id, account_id=accounts[4].id, name="외부", role=MemberRole.OWNER),
            Member(club_id=clubs[0].id, name="명단 전용", role=MemberRole.MEMBER),
        ])
        expires = datetime.now(UTC) + timedelta(hours=1)
        session.add_all([
            Auth(account_id=account.id, access_token_hash=hash_token(token), access_token_expires_at=expires,
                 refresh_token_hash=hash_token(token + "-refresh"), expires_at=expires)
            for account, token in zip(accounts, tokens, strict=True)
        ])
        job = AgentJob(club_id=clubs[0].id, kind=AgentJobKind.CONTEXT_DECISION, status=AgentJobStatus.SUCCEEDED)
        session.add(job)
        await session.flush()
        owner_id = await session.scalar(select(Member.id).where(Member.account_id == accounts[0].id))
        meeting = Meeting(club_id=clubs[0].id, created_by=owner_id, title="확인 테스트 회의")
        other_meeting = Meeting(club_id=clubs[0].id, created_by=owner_id, title="다른 회의")
        session.add_all([meeting, other_meeting])
        await session.flush()
        segment = TranscriptSegment(meeting_id=meeting.id, seq=1, text="발표 자료를 준비하자", is_final=True, change_seq=1)
        session.add(segment)
        await session.flush()
        decision = ContextDecision(
            club_id=clubs[0].id, job_id=job.id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
            meeting_id=meeting.id, sources=[{"sourceId": segment.id, "sourceVersion": 1}],
            status=ContextDecisionStatus.SUCCEEDED, route=JudgeRoute.NONE, kind=JudgeKind.NO_LOOKUP,
            tool_calls=[], model_version="test", policy_version="test",
        )
        session.add(decision)
        await session.flush()
        suggestion = TaskSuggestion(club_id=clubs[0].id, decision_id=decision.id,
                                    source_type=ContextSourceType.MEETING_TRANSCRIPT,
                                    title="발표 자료 준비", evidence=decision.sources)
        session.add(suggestion)
        await session.commit()
        data = {"club": clubs[0].id, "suggestion": suggestion.id, "decision": decision.id,
                "meeting": meeting.id, "otherMeeting": other_meeting.id, "segment": segment.id,
                "accounts": [account.id for account in accounts],
                "headers": [{"Authorization": f"Bearer {token}"} for token in tokens]}
    yield data
    async with db_session.get_sessionmaker()() as session:
        await session.execute(delete(Club).where(Club.id.in_([club.id for club in clubs])))
        await session.execute(delete(Account).where(Account.id.in_([account.id for account in accounts])))
        await session.commit()


def _body(case: dict) -> dict:
    now = datetime.now(UTC)
    return {"expectedVersion": 1, "kind": "TASK", "title": "발표 자료 최종 확인",
            "dueAt": (now + timedelta(days=1)).isoformat(), "timezone": "Asia/Seoul",
            "reminderAt": (now + timedelta(hours=1)).isoformat(),
            "recipientAccountIds": [case["accounts"][1]]}


def _confirm(client: TestClient, case: dict, body: dict | None = None):
    return client.post(f"/api/v1/clubs/{case['club']}/task-suggestions/{case['suggestion']}/confirm",
                       headers=case["headers"][0], json=body or _body(case))


async def test_confirmation_retry_stores_one_item_and_one_reminder(client: TestClient, case: dict) -> None:
    body = _body(case)
    first = _confirm(client, case, body)
    assert first.status_code == 200, first.text
    item = first.json()["data"]
    assert item["reminder"]["status"] == "PENDING" and item["reminder"]["acceptedCount"] == 0
    assert item["dueAt"].endswith("Z") and item["timezone"] == "Asia/Seoul"
    again = _confirm(client, case, body)
    assert again.status_code == 200, again.text
    assert again.json()["data"]["id"] == item["id"]
    assert again.json()["data"]["reminder"]["id"] == item["reminder"]["id"]
    changed = _confirm(client, case, {**body, "title": "다른 확인"})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    async with db_session.get_sessionmaker()() as session:
        for model in (ConfirmedTask, TaskReminder):
            assert await session.scalar(select(func.count()).select_from(model).where(model.club_id == case["club"])) == 1


async def test_accept_alone_does_not_reserve_and_can_then_be_explicitly_confirmed(client: TestClient, case: dict) -> None:
    accepted = client.post(f"/api/v1/clubs/{case['club']}/task-suggestions/{case['suggestion']}/accept",
                           headers=case["headers"][0], json={"expectedVersion": 1})
    assert accepted.status_code == 200, accepted.text
    empty = client.get(f"/api/v1/clubs/{case['club']}/confirmed-tasks", headers=case["headers"][0])
    assert empty.json()["data"] == []
    saved = _confirm(client, case, {**_body(case), "expectedVersion": 2})
    assert saved.status_code == 200, saved.text


async def test_ordinary_foreign_or_pending_recipient_and_past_time_cannot_reserve(client: TestClient, case: dict) -> None:
    body = _body(case)
    for invalid_account in case["accounts"][2:]:
        response = _confirm(client, case, {**body, "recipientAccountIds": [invalid_account]})
        assert response.status_code == 422 and "recipientAccountIds" in response.json()["error"]["fields"]
    past = _confirm(client, case, {**body, "reminderAt": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()})
    assert past.status_code == 422 and "reminderAt" in past.json()["error"]["fields"]
    empty = client.get(f"/api/v1/clubs/{case['club']}/confirmed-tasks", headers=case["headers"][0])
    assert empty.json()["data"] == []


async def test_update_replaces_pending_reservation_and_cancel_stops_it(client: TestClient, case: dict) -> None:
    first = _confirm(client, case).json()["data"]
    body = {**_body(case), "expectedVersion": first["version"], "title": "수정 내용", "recipientAccountIds": [case["accounts"][0]]}
    url = f"/api/v1/clubs/{case['club']}/confirmed-tasks/{first['id']}"
    updated = client.patch(url, headers=case["headers"][1], json=body)
    assert updated.status_code == 200, updated.text
    item = updated.json()["data"]
    assert item["title"] == "수정 내용" and item["version"] == first["version"] + 1
    assert item["reminder"]["id"] == first["reminder"]["id"]
    assert item["reminder"]["recipientAccountIds"] == [case["accounts"][0]]
    stale = client.patch(url, headers=case["headers"][0], json=body)
    assert stale.status_code == 409
    cancelled = client.post(url + "/cancel", headers=case["headers"][0], json={"expectedVersion": item["version"]})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == cancelled.json()["data"]["reminder"]["status"] == "CANCELLED"


async def test_only_active_chair_and_officers_are_recipients_and_service_users(client: TestClient, case: dict) -> None:
    base = f"/api/v1/clubs/{case['club']}"
    recipients = client.get(base + "/reminder-recipients", headers=case["headers"][1])
    assert recipients.status_code == 200, recipients.text
    rows = recipients.json()["data"]
    assert {row["accountId"] for row in rows} == set(case["accounts"][:2])
    assert {row["role"] for row in rows} == {"OWNER", "MANAGER"}
    assert set(rows[0]) == {"accountId", "memberId", "name", "role"}
    for path in ("/reminder-recipients", "/confirmed-tasks", "/task-suggestions"):
        forbidden = client.get(base + path, headers=case["headers"][2])
        assert forbidden.status_code == 403
    forbidden_confirm = client.post(base + f"/task-suggestions/{case['suggestion']}/confirm", headers=case["headers"][2], json=_body(case))
    assert forbidden_confirm.status_code == 403
    outsider = client.get(base + "/confirmed-tasks", headers=case["headers"][4])
    assert outsider.status_code == 403


async def test_sending_blocks_cancel_and_service_accepted_result_is_preserved(client: TestClient, case: dict) -> None:
    item = _confirm(client, case).json()["data"]
    url = f"/api/v1/clubs/{case['club']}/confirmed-tasks/{item['id']}"
    async with db_session.get_sessionmaker()() as session:
        reminder = await session.get(TaskReminder, item["reminder"]["id"])
        reminder.status = "SENDING"
        await session.commit()
    blocked = client.post(url + "/cancel", headers=case["headers"][0], json={"expectedVersion": item["version"]})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "REMINDER_DISPATCH_IN_PROGRESS"
    async with db_session.get_sessionmaker()() as session:
        reminder = await session.get(TaskReminder, item["reminder"]["id"])
        reminder.status = "SERVICE_ACCEPTED"
        reminder.accepted_count = 1
        reminder.attempted_at = datetime.now(UTC)
        await session.commit()
    cancelled = client.post(url + "/cancel", headers=case["headers"][0], json={"expectedVersion": item["version"]})
    assert cancelled.status_code == 200, cancelled.text
    result = cancelled.json()["data"]
    assert result["status"] == "CANCELLED" and result["reminder"]["status"] == "SERVICE_ACCEPTED"
    assert result["reminder"]["acceptedCount"] == 1


async def test_concurrent_confirmation_is_serialized_and_reuses_reservation(case: dict) -> None:
    body = TaskSuggestionConfirmIn.model_validate(_body(case))
    async with db_session.get_sessionmaker()() as session:
        owner_id = await session.scalar(select(Member.id).where(Member.account_id == case["accounts"][0]))

    async def save() -> tuple[str, str]:
        async with db_session.get_sessionmaker()() as session:
            item = await confirm_suggestion(session, club_id=case["club"],
                                            suggestion_id=case["suggestion"],
                                            confirmed_by=owner_id, body=body)
            return item.id, item.reminder.id

    first, second = await asyncio.gather(save(), save())
    assert first == second
    async with db_session.get_sessionmaker()() as session:
        assert await session.scalar(select(func.count()).select_from(TaskReminder).where(TaskReminder.club_id == case["club"])) == 1


async def test_assignee_is_separate_from_recipients_and_restricted_to_club(case: dict, client: TestClient) -> None:
    body = {**_body(case), "assigneeName": "이름만 확인한 담당자"}
    for invalid_account in case["accounts"][2:]:
        bad = _confirm(client, case, {**body, "assigneeAccountId": invalid_account})
        assert bad.status_code == 422 and "assigneeAccountId" in bad.json()["error"]["fields"]
    saved = _confirm(client, case, body)
    assert saved.status_code == 200, saved.text
    item = saved.json()["data"]
    assert item["assigneeName"] == "이름만 확인한 담당자" and item["assigneeAccountId"] is None
    url = f"/api/v1/clubs/{case['club']}/confirmed-tasks/{item['id']}"
    updated = client.patch(url, headers=case["headers"][0], json={
        **body, "expectedVersion": item["version"], "assigneeName": "대표",
        "assigneeAccountId": case["accounts"][0],
    })
    assert updated.status_code == 200, updated.text
    result = updated.json()["data"]
    assert result["assigneeAccountId"] == case["accounts"][0]
    assert case["accounts"][0] not in result["reminder"]["recipientAccountIds"]
    for field in ("assigneeAccountId", "recipientAccountIds"):
        invalid_value = case["accounts"][2] if field == "assigneeAccountId" else [case["accounts"][2]]
        rejected = client.patch(url, headers=case["headers"][0], json={
            **body, "expectedVersion": result["version"], field: invalid_value,
        })
        assert rejected.status_code == 422 and field in rejected.json()["error"]["fields"]
    preserved = client.get(url, headers=case["headers"][0]).json()["data"]
    assert preserved == result


async def test_candidate_exact_time_and_unresolved_fields_are_preserved(case: dict, client: TestClient) -> None:
    at = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)
    async with db_session.get_sessionmaker()() as session:
        suggestion = await session.get(TaskSuggestion, case["suggestion"])
        suggestion.kind = "SCHEDULE"
        suggestion.scheduled_at = at
        suggestion.suggested_assignee = "미매칭 이름"
        suggestion.unresolved_fields = ["assignee", "reminderAt"]
        await session.commit()
    response = client.get(f"/api/v1/clubs/{case['club']}/task-suggestions", headers=case["headers"][0])
    assert response.status_code == 200, response.text
    suggestion = response.json()["data"][0]
    assert suggestion["kind"] == "SCHEDULE" and suggestion["dueAt"] is None
    assert suggestion["scheduledAt"] == at.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert suggestion["suggestedAssignee"] == "미매칭 이름"
    assert suggestion["unresolvedFields"] == ["assignee", "reminderAt"]


async def test_meeting_filter_and_stale_first_confirmation(case: dict, client: TestClient) -> None:
    base = f"/api/v1/clubs/{case['club']}"
    for meeting, count in ((case["meeting"], 1), (case["otherMeeting"], 0)):
        response = client.get(base + f"/task-suggestions?meetingId={meeting}", headers=case["headers"][0])
        assert response.status_code == 200, response.text
        assert len(response.json()["data"]) == count
    async with db_session.get_sessionmaker()() as session:
        segment = await session.get(TranscriptSegment, case["segment"])
        segment.version += 1
        await session.commit()
    stale = _confirm(client, case)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "TASK_SUGGESTION_STALE"
    async with db_session.get_sessionmaker()() as session:
        segment = await session.get(TranscriptSegment, case["segment"])
        segment.version = 1
        decision = await session.get(ContextDecision, case["decision"])
        decision.status = ContextDecisionStatus.STALE
        await session.commit()
    stale = _confirm(client, case)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "TASK_SUGGESTION_STALE"


async def test_confirmed_meeting_filter_and_idempotent_retry_after_source_change(case: dict, client: TestClient) -> None:
    body = _body(case)
    first = _confirm(client, case, body)
    assert first.status_code == 200, first.text
    async with db_session.get_sessionmaker()() as session:
        decision = await session.get(ContextDecision, case["decision"])
        decision.status = ContextDecisionStatus.STALE
        await session.commit()
    again = _confirm(client, case, body)
    assert again.status_code == 200 and again.json()["data"]["id"] == first.json()["data"]["id"]
    base = f"/api/v1/clubs/{case['club']}/confirmed-tasks"
    for meeting, count in ((case["meeting"], 1), (case["otherMeeting"], 0)):
        response = client.get(base + f"?meetingId={meeting}", headers=case["headers"][0])
        assert response.status_code == 200, response.text
        assert len(response.json()["data"]) == count


async def test_토리_본인_확정_할일만_조회하고_소속을_검증한다(client, case, monkeypatch):
    import app.ai as ai
    body = _body(case)
    body['assigneeAccountId'] = case['accounts'][0]
    response = client.post(f"/api/v1/clubs/{case['club']}/task-suggestions/{case['suggestion']}/confirm", headers=case['headers'][0], json=body)
    assert response.status_code == 200, response.text
    async def classify(_request):
        return ai.ToriIntentResult(intent='task_list', scope='self', kind='task')
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    url = f"/api/v1/clubs/{case['club']}/tori/messages"
    result = client.post(url, headers=case['headers'][0], json={'message':'내 할 일'})
    assert result.status_code == 200, result.text
    assert [item['title'] for item in result.json()['data']['tasks']['items']] == [body['title']]
    assert result.json()['data']['tasks']['scope'] == 'self'
    other = client.post(url, headers=case['headers'][1], json={'message':'내 할 일'})
    assert other.status_code == 200 and other.json()['data']['tasks']['items'] == []
    assert client.post(url, headers=case['headers'][4], json={'message':'내 할 일'}).status_code == 403
    assert client.post(url, json={'message':'내 할 일'}).status_code == 401


async def test_토리_화면이동과_지원불가_요청은_변경하지_않는다(client, case, monkeypatch):
    import app.ai as ai
    async def classify(request):
        return ai.ToriIntentResult(intent='meeting' if request.message == '회의' else 'unsupported')
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    url = f"/api/v1/clubs/{case['club']}/tori/messages"
    meeting = client.post(url, headers=case['headers'][0], json={'message':'회의'})
    denied = client.post(url, headers=case['headers'][0], json={'message':'알림 예약'})
    assert meeting.status_code == denied.status_code == 200
    assert meeting.json()['data']['navigation'] == '/meetings'
    assert denied.json()['data']['intent'] == 'unsupported'
    assert denied.json()['data']['navigation'] is None
    after = client.get(f"/api/v1/clubs/{case['club']}/confirmed-tasks", headers=case['headers'][0])
    assert after.json()['data'] == []
