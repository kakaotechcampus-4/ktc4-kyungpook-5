"""토리 카드 답: 행사 현황·승인 대기·확인할 일·회의 할 일과, 이름으로 행사·회의를 찾는 규칙."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import ai
from app.core.enums import (
    AgentJobKind,
    AgentJobStatus,
    ContextDecisionStatus,
    ContextSourceType,
    EventStatus,
    ExpenseSource,
    JudgeKind,
    JudgeRoute,
    MeetingStatus,
)
from app.db import session as db_session
from app.models.accounting import Expense
from app.models.agent import AgentJob, ContextDecision
from app.models.clubs import Member
from app.models.events import Event
from app.models.meetings import Meeting
from app.models.reminders import ConfirmedTask
from app.models.tasks import TaskSuggestion
from app.services.event_service import today_kst
from tests.integration.event_seed import add_action, add_event, add_step, owner_with_club

pytestmark = [pytest.mark.db, pytest.mark.anyio]

KST = ZoneInfo("Asia/Seoul")
DONE_AT = datetime(2026, 3, 1, tzinfo=UTC)


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _at(days: int, hour: int = 18) -> datetime:
    return datetime.combine(today_kst() + timedelta(days=days), time(hour), KST)


def _ask(client: TestClient, headers: dict, club_id: str, monkeypatch, result: ai.ToriIntentResult) -> dict:
    async def classify(_request):
        return result

    monkeypatch.setattr(ai, "classify_tori_intent", classify)
    response = client.post(f"/api/v1/clubs/{club_id}/tori/messages", headers=headers, json={"message": "질문"})
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _owner_member(club_id: str) -> str:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(Member.id).where(Member.club_id == club_id))


@pytest.fixture
async def events(client: TestClient, app_db) -> dict:
    headers, club_id = owner_with_club(client, "tori-lookup")
    spring = await add_event(club_id, title="2026 봄 MT", start_date=today_kst() + timedelta(days=20))
    await add_event(club_id, title="2025 봄 MT", status=EventStatus.COMPLETE,
                    start_date=today_kst() - timedelta(days=200))
    hackathon = await add_event(club_id, title="가을 해커톤", start_date=today_kst() + timedelta(days=40))
    await add_event(club_id, title="겨울 캠프", status=EventStatus.PLANNING)

    await add_step(spring, 1, name="장소 예약", completed_at=DONE_AT)
    current = await add_step(spring, 2, name="참가비 걷기", deadline=_at(2))
    await add_step(spring, 3, name="공지 발송", deadline=_at(7))
    await add_step(spring, 4, name="버스 예약")
    await add_step(spring, 5, name="정산")
    await add_action(spring, step_id=current, title="참가비 안내 공지")
    await add_action(spring, step_id=current, title="입금 독촉 공지")
    await add_step(hackathon, 1, name="후원사 연락")

    async with db_session.get_sessionmaker()() as session:
        event = await session.get(Event, spring)
        event.budget_total = 1_000_000
        member = await _owner_member(club_id)
        session.add_all([
            Expense(club_id=club_id, event_id=spring, spent_at=_at(-3), amount=250_000,
                    source=ExpenseSource.MANUAL, created_by=member),
            Expense(club_id=club_id, event_id=spring, spent_at=_at(-1), amount=50_000,
                    source=ExpenseSource.MANUAL, created_by=member),
            Expense(club_id=club_id, event_id=hackathon, spent_at=_at(-1), amount=9_999,
                    source=ExpenseSource.MANUAL, created_by=member),
        ])
        await session.commit()
    return {"headers": headers, "club": club_id, "spring": spring, "hackathon": hackathon}


async def test_행사_현황은_진행_중인_같은_이름_행사를_고르고_단계와_예산을_보여준다(client, events, monkeypatch):
    data = _ask(client, events["headers"], events["club"], monkeypatch,
                ai.ToriIntentResult(intent="event_status", target="봄 MT"))
    assert data["reply"] == "2026 봄 MT, 지금 참가비 걷기 단계를 진행하고 있어요. 승인을 기다리는 일이 2건 있어요."
    card = data["card"]
    assert card["type"] == "event_status" and card["event"]["id"] == events["spring"]
    assert card["currentStep"] == {"name": "참가비 걷기", "dueDate": (today_kst() + timedelta(days=2)).isoformat()}
    assert [step["name"] for step in card["nextSteps"]] == ["공지 발송", "버스 예약"]
    assert card["approvals"] == ["참가비 안내 공지", "입금 독촉 공지"] and card["approvalCount"] == 2
    assert (card["budget"], card["spent"]) == (1_000_000, 300_000)
    assert data["suggestions"] == ["승인 기다리는 거 보여줘", "가을 해커톤 어디까지 됐어?"]


async def test_행사_이름이_없거나_못_찾으면_되묻거나_진행_중인_행사를_보여준다(client, events, monkeypatch):
    def ask(target):
        return _ask(client, events["headers"], events["club"], monkeypatch,
                    ai.ToriIntentResult(intent="event_status", target=target))

    unnamed = ask(None)  # 진행 중인 행사가 둘이라 고르게 한다
    assert unnamed["reply"] == "어느 행사요? 맞는 행사가 2개 있어요." and unnamed["card"] is None
    assert unnamed["suggestions"] == ["2026 봄 MT 어디까지 됐어?", "가을 해커톤 어디까지 됐어?"]

    picked = ask("2026 봄 MT")  # 되묻기 버튼으로 다시 물으면 한 행사로 좁혀진다
    assert picked["card"]["event"]["id"] == events["spring"]

    missing = ask("축제")
    assert missing["reply"] == "'축제' 행사를 찾지 못했어요. 진행 중인 행사는 이렇게 있어요."
    assert [event["title"] for event in missing["card"]["events"]] == ["2026 봄 MT", "가을 해커톤"]

    planning = ask("겨울 캠프")
    assert planning["reply"] == "겨울 캠프, 아직 계획 중이에요. 운영을 시작하면 단계 진행을 볼 수 있어요."
    assert planning["card"]["currentStep"] is None and planning["card"]["nextSteps"] == []


async def test_같은_이름_행사만_남으면_가장_최근_행사를_본다(client, app_db, monkeypatch):
    headers, club_id = owner_with_club(client, "tori-lookup-same")
    await add_event(club_id, title="정기 MT", start_date=today_kst() - timedelta(days=300))
    recent = await add_event(club_id, title="정기 MT", start_date=today_kst() + timedelta(days=30))
    data = _ask(client, headers, club_id, monkeypatch, ai.ToriIntentResult(intent="event_status", target="정기 MT"))
    assert data["card"]["event"]["id"] == recent


async def test_승인_대기와_확인할_일(client, events, monkeypatch):
    approvals = _ask(client, events["headers"], events["club"], monkeypatch,
                     ai.ToriIntentResult(intent="approval_list"))
    assert approvals["reply"] == "승인을 기다리는 일이 2건 있어요. 행사 상세에서 내용을 보고 승인할 수 있어요."
    [group] = approvals["card"]["groups"]
    assert group["eventId"] == events["spring"]
    assert [(a["title"], a["stepName"]) for a in group["actions"]] == [
        ("참가비 안내 공지", "참가비 걷기"), ("입금 독촉 공지", "참가비 걷기"),
    ]
    assert approvals["suggestions"] == ["2026 봄 MT 어디까지 됐어?"]

    none = _ask(client, events["headers"], events["club"], monkeypatch,
                ai.ToriIntentResult(intent="approval_list", target="해커톤"))
    assert none["reply"] == "가을 해커톤에서 승인을 기다리는 일이 없어요." and none["card"] is None

    briefing = _ask(client, events["headers"], events["club"], monkeypatch, ai.ToriIntentResult(intent="briefing"))
    assert briefing["reply"] == "오늘 확인할 일 2개를 급한 순서로 모았어요."
    assert [item["kind"] for item in briefing["card"]["items"]] == ["approval", "deadline"]
    assert briefing["suggestions"] == ["승인 기다리는 거 보여줘"]


async def _meeting_with_tasks(club_id: str, member: str, *, title: str | None, started: datetime,
                              status: MeetingStatus, tasks: list[tuple[str, str, datetime | None]]) -> str:
    async with db_session.get_sessionmaker()() as session:
        job = AgentJob(club_id=club_id, kind=AgentJobKind.CONTEXT_DECISION, status=AgentJobStatus.SUCCEEDED)
        meeting = Meeting(club_id=club_id, created_by=member, title=title, status=status, started_at=started)
        session.add_all([job, meeting])
        await session.flush()
        decision = ContextDecision(
            club_id=club_id, job_id=job.id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
            meeting_id=meeting.id, sources=[], status=ContextDecisionStatus.SUCCEEDED,
            route=JudgeRoute.NONE, kind=JudgeKind.NO_LOOKUP, tool_calls=[],
            model_version="test", policy_version="test",
        )
        session.add(decision)
        await session.flush()
        for index, (task_title, kind, due) in enumerate(tasks):
            suggestion = TaskSuggestion(club_id=club_id, decision_id=decision.id,
                                        source_type=ContextSourceType.MEETING_TRANSCRIPT,
                                        title=task_title, evidence=[])
            session.add(suggestion)
            await session.flush()
            session.add(ConfirmedTask(
                club_id=club_id, suggestion_id=suggestion.id, source_version=1,
                confirmation_hash=f"{meeting.id}{index}".ljust(64, "0"), kind=kind, title=task_title,
                assignee_name="김민지", due_at=due if kind == "TASK" else None,
                scheduled_at=due if kind == "SCHEDULE" else None, timezone="Asia/Seoul",
            ))
        await session.commit()
        return meeting.id


async def test_회의_할_일은_지난_회의와_이름_날짜로_찾는다(client, app_db, monkeypatch):
    headers, club_id = owner_with_club(client, "tori-meeting")
    member = await _owner_member(club_id)
    november = await _meeting_with_tasks(
        club_id, member, title="11월 정기 회의", started=_at(-2, 19), status=MeetingStatus.COMPLETED,
        tasks=[("버스 견적 받기", "TASK", _at(-1)), ("다음 회의", "SCHEDULE", _at(5)), ("장부 정리", "TASK", _at(1))])
    october = await _meeting_with_tasks(
        club_id, member, title="10월 정기 회의", started=_at(-30, 19), status=MeetingStatus.COMPLETED,
        tasks=[("숙소 알아보기", "TASK", None)])
    await _meeting_with_tasks(club_id, member, title="지금 회의", started=_at(0, 0), status=MeetingStatus.RECORDING,
                              tasks=[])

    def ask(**fields):
        return _ask(client, headers, club_id, monkeypatch, ai.ToriIntentResult(intent="meeting_tasks", **fields))

    latest = ask()  # "지난 회의 할 일": 녹음 중인 회의는 건너뛴다
    assert latest["reply"] == "11월 정기 회의에서 확정한 할 일이 3개 있어요. 마감이 지난 일이 1개 있어요."
    card = latest["card"]
    assert card["type"] == "tasks" and card["meetingId"] == november
    assert [task["title"] for task in card["tasks"]] == ["버스 견적 받기", "장부 정리", "다음 회의"]

    choose = ask(target="정기 회의")
    october_day = today_kst() - timedelta(days=30)
    november_day = today_kst() - timedelta(days=2)
    assert choose["reply"] == "어느 회의요? 맞는 회의가 2개 있어요."
    assert choose["suggestions"] == [
        f"{november_day.month}월 {november_day.day}일 11월 정기 회의에서 정한 할 일",
        f"{october_day.month}월 {october_day.day}일 10월 정기 회의에서 정한 할 일",
    ]
    by_date = ask(target="운영회의", meeting_date=october_day)  # 날짜가 맞으면 이름이 달라도 그 회의
    assert by_date["card"]["meetingId"] == october
    assert by_date["reply"] == "10월 정기 회의에서 확정한 할 일이 1개 있어요."

    missing = ask(target="운영회의")
    assert missing["reply"] == "'운영회의' 회의를 찾지 못했어요." and missing["card"] is None
