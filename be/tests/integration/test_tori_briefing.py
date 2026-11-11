"""메인 탭 브리핑 API: 오늘 확인할 일을 모으는 범위와 순서, 소속 검사."""

from collections.abc import AsyncIterator
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import (
    ActionStatus,
    ActionType,
    AgentJobKind,
    AgentJobStatus,
    ContextDecisionStatus,
    ContextSourceType,
    EventStatus,
    JudgeKind,
    JudgeRoute,
    MemberRole,
)
from app.db import session as db_session
from app.models.agent import AgentJob, ContextDecision
from app.models.clubs import Member
from app.models.meetings import Meeting
from app.models.reminders import ConfirmedTask
from app.models.tasks import TaskSuggestion
from app.services.event_service import today_kst
from tests.integration.event_seed import (
    add_action,
    add_event,
    add_step,
    owner_with_club,
    signup_and_login,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]

KST = ZoneInfo("Asia/Seoul")
DONE_AT = datetime(2026, 3, 1, tzinfo=KST)


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _at(days: int) -> datetime:
    """오늘(한국 날짜)에서 days일 뒤 18시."""
    return datetime.combine(today_kst() + timedelta(days=days), time(18), KST)


def _club(client: TestClient, tag: str) -> tuple[str, dict, str]:
    account_id, headers = signup_and_login(client, tag)
    club = client.post("/api/v1/clubs", headers=headers, json={"name": f"{tag} 동아리"})
    assert club.status_code == 201, club.text
    return account_id, headers, club.json()["data"]["id"]


async def _add_tasks(club_id: str, owner_account: str, other_account: str) -> dict[str, str]:
    """회의에서 나온 확정 할 일. 본인 배정·남 배정·취소·일정 하나씩, 회의 없는 할 일 하나."""
    async with db_session.get_sessionmaker()() as session:
        owner_member = await session.scalar(
            select(Member.id).where(Member.club_id == club_id, Member.account_id == owner_account)
        )
        job = AgentJob(club_id=club_id, kind=AgentJobKind.CONTEXT_DECISION, status=AgentJobStatus.SUCCEEDED)
        meeting = Meeting(club_id=club_id, created_by=owner_member, title="11월 정기 회의")
        session.add_all([job, meeting])
        await session.flush()

        def decision(meeting_id: str | None) -> ContextDecision:
            return ContextDecision(
                club_id=club_id, job_id=job.id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
                meeting_id=meeting_id, sources=[], status=ContextDecisionStatus.SUCCEEDED,
                route=JudgeRoute.NONE, kind=JudgeKind.NO_LOOKUP, tool_calls=[],
                model_version="test", policy_version="test",
            )

        with_meeting, without_meeting = decision(meeting.id), decision(None)
        session.add_all([with_meeting, without_meeting])
        await session.flush()
        ids: dict[str, str] = {}
        rows = [
            ("today", with_meeting, owner_account, "TASK", "ACTIVE", _at(0)),
            ("later", with_meeting, owner_account, "TASK", "ACTIVE", _at(9)),
            ("undated", without_meeting, owner_account, "TASK", "ACTIVE", None),
            ("others", with_meeting, other_account, "TASK", "ACTIVE", _at(0)),
            ("cancelled", with_meeting, owner_account, "TASK", "CANCELLED", _at(0)),
            ("schedule", with_meeting, owner_account, "SCHEDULE", "ACTIVE", None),
        ]
        for key, source, assignee, kind, status, due in rows:
            suggestion = TaskSuggestion(club_id=club_id, decision_id=source.id,
                                        source_type=ContextSourceType.MEETING_TRANSCRIPT,
                                        title=key, evidence=[])
            session.add(suggestion)
            await session.flush()
            task = ConfirmedTask(
                club_id=club_id, suggestion_id=suggestion.id, source_version=1,
                confirmation_hash=key.ljust(64, "0"), kind=kind, title=f"할 일 {key}",
                assignee_account_id=assignee, due_at=due,
                scheduled_at=_at(1) if kind == "SCHEDULE" else None,
                timezone="Asia/Seoul", status=status,
            )
            session.add(task)
            await session.flush()
            ids[key] = task.id
        ids["meeting"] = meeting.id
        await session.commit()
    return ids


async def test_브리핑은_마감_승인_내_할_일을_급한_순서로_모은다(client: TestClient, app_db) -> None:
    owner_account, headers, club_id = _club(client, "briefing-owner")
    other_account, _ = signup_and_login(client, "briefing-other")
    async with db_session.get_sessionmaker()() as session:
        session.add(Member(club_id=club_id, account_id=other_account, name="운영진", role=MemberRole.MANAGER))
        await session.commit()

    mt = await add_event(club_id, title="봄 MT", start_date=today_kst() + timedelta(days=20))
    await add_step(mt, 1, name="장소 예약", completed_at=DONE_AT, deadline=_at(-5))
    overdue = await add_step(mt, 2, name="참가비 걷기", deadline=_at(-1))
    await add_step(mt, 3, name="공지 발송", deadline=_at(1))
    await add_step(mt, 4, name="정산", deadline=_at(10))
    await add_action(mt, step_id=overdue, title="참가비 안내 공지", due_date=None)
    await add_action(mt, step_id=overdue, title="입금 독촉 공지")
    await add_action(mt, step_id=overdue, title="참여 확인", type=ActionType.CONFIRMATION)
    await add_action(mt, step_id=overdue, title="이미 승인", status=ActionStatus.APPROVED)

    planning = await add_event(club_id, title="가을 해커톤", status=EventStatus.PLANNING)
    planned = await add_step(planning, 1, name="후원사 연락", deadline=_at(0))
    await add_action(planning, step_id=planned, title="계획 중 공지")
    await add_event(club_id, title="지난 행사", status=EventStatus.COMPLETE)

    _outsider_headers, outsider_club = owner_with_club(client, "briefing-outsider")
    foreign = await add_event(outsider_club, title="다른 동아리 행사")
    await add_step(foreign, 1, name="남의 단계", deadline=_at(0))

    tasks = await _add_tasks(club_id, owner_account, other_account)

    response = client.get(f"/api/v1/clubs/{club_id}/tori/briefing", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [(item["kind"], item["title"]) for item in data["items"]] == [
        ("deadline", "참가비 걷기 단계 마감"),  # 어제 마감(지남)
        ("task", "할 일 today"),               # 오늘
        ("approval", "참가비 안내 공지"),         # 기한 없는 승인 대기
        ("deadline", "공지 발송 단계 마감"),      # 내일
        ("task", "할 일 later"),               # 9일 뒤도 내 할 일이면 넣는다
        ("task", "할 일 undated"),             # 기한 없는 할 일은 맨 뒤
    ]
    by_title = {item["title"]: item for item in data["items"]}
    approval = by_title["참가비 안내 공지"]
    assert approval["moreCount"] == 1
    assert approval["source"] == "봄 MT | 참가비 걷기 단계"
    assert approval["eventId"] == mt and approval["ask"] == "승인 기다리는 거 보여줘"
    deadline = by_title["공지 발송 단계 마감"]
    assert deadline["dueDate"] == (today_kst() + timedelta(days=1)).isoformat()
    assert deadline["source"] == "봄 MT" and deadline["ask"] == "봄 MT 어디까지 됐어?"
    task = by_title["할 일 today"]
    assert task["taskId"] == tasks["today"] and task["meetingId"] == tasks["meeting"]
    assert task["source"] == "11월 정기 회의" and task["ask"] == "11월 정기 회의에서 정한 할 일"
    undated = by_title["할 일 undated"]
    assert undated["meetingId"] is None and undated["ask"] is None and undated["dueDate"] is None
    assert [(event["title"], event["status"]) for event in data["events"]] == [
        ("봄 MT", "ON_GOING"), ("가을 해커톤", "PLANNING"),
    ]
    assert data["events"][0]["pendingApprovalCount"] == 2


async def test_브리핑은_본인_할_일만_보이고_소속을_검사한다(client: TestClient, app_db) -> None:
    owner_account, headers, club_id = _club(client, "briefing-scope")
    other_account, other_headers = signup_and_login(client, "briefing-scope-member")
    async with db_session.get_sessionmaker()() as session:
        session.add(Member(club_id=club_id, account_id=other_account, name="운영진", role=MemberRole.MANAGER))
        await session.commit()
    await _add_tasks(club_id, owner_account, other_account)
    url = f"/api/v1/clubs/{club_id}/tori/briefing"

    other = client.get(url, headers=other_headers)
    assert other.status_code == 200, other.text
    assert [item["title"] for item in other.json()["data"]["items"]] == ["할 일 others"]

    outsider_headers, _ = owner_with_club(client, "briefing-scope-outsider")
    assert client.get(url, headers=outsider_headers).status_code == 403
    assert client.get(url).status_code == 401
