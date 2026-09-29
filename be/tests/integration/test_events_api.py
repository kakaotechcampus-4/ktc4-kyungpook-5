"""계획 시작·임시 저장 목록 API (이슈 #63).

실제 DB에 저장하고 조회한다. 테스트마다 롤백되어 서로 영향을 주지 않는다.
"""

import re
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventStatus, MessageRole, StepActor, StepPhase
from app.models import Club, Conversation, Event, Message, Step

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CLUB_ID = "clb_3a71c0"  # alembic 시드
EVENTS_URL = "/api/v1/events"
DRAFTS_URL = "/api/v1/events/drafts"
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


async def test_db_session_commit_is_rolled_back_after_test_1(
    db_session: AsyncSession,
) -> None:
    db_session.add(Event(club_id=CLUB_ID, title="격리 확인"))
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count()).select_from(Event).where(Event.title == "격리 확인")
    )
    assert count == 1


async def test_db_session_commit_is_rolled_back_after_test_2(
    db_session: AsyncSession,
) -> None:
    count = await db_session.scalar(
        select(func.count()).select_from(Event).where(Event.title == "격리 확인")
    )
    assert count == 0


async def test_create_event_returns_201_with_first_greeting(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        EVENTS_URL, json={"clubId": CLUB_ID, "title": "봄 MT"}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"] is None
    data = body["data"]
    assert set(data) == {"id", "title", "status", "conversationId", "messages"}
    assert data["id"].startswith("evt_")
    assert data["title"] == "봄 MT"
    assert data["status"] == "PLANNING"
    assert data["conversationId"].startswith("cnv_")
    [greeting] = data["messages"]
    assert set(greeting) == {"id", "role", "content", "createdAt"}
    assert greeting["role"] == "ASSISTANT"
    assert greeting["content"] == "어떤 행사를 준비하시나요?"
    assert ISO_UTC.match(greeting["createdAt"])


async def test_create_event_saves_event_conversation_and_message(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    response = await api_client.post(EVENTS_URL, json={"clubId": CLUB_ID})
    data = response.json()["data"]

    event = await db_session.get(Event, data["id"])
    conversation = await db_session.get(Conversation, data["conversationId"])
    message = await db_session.get(Message, data["messages"][0]["id"])
    assert event.status == EventStatus.PLANNING
    assert event.club_id == CLUB_ID
    assert conversation.event_id == event.id
    assert conversation.member_id == "mbr_3a71c0"
    assert message.conversation_id == conversation.id
    assert (message.seq, message.role) == (1, MessageRole.ASSISTANT)


@pytest.mark.parametrize(
    "payload", [{"clubId": CLUB_ID}, {"clubId": CLUB_ID, "title": "  "}]
)
async def test_create_event_without_title_uses_default(
    api_client: httpx.AsyncClient, payload: dict
) -> None:
    response = await api_client.post(EVENTS_URL, json=payload)

    assert re.fullmatch(r"새 행사 · \d{1,2}월 \d{1,2}일", response.json()["data"]["title"])


async def test_create_event_with_unknown_club_is_validation_error(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(EVENTS_URL, json={"clubId": "clb_없는동아리"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert "clubId" in error["fields"]


async def test_create_event_requires_club_id(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(EVENTS_URL, json={"title": "봄 MT"})

    assert response.status_code == 422
    assert "clubId" in response.json()["error"]["fields"]


def _at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, tzinfo=UTC)


async def _event(
    session: AsyncSession,
    *,
    title: str,
    saved_at: datetime | None,
    status: EventStatus = EventStatus.PLANNING,
    club_id: str = CLUB_ID,
) -> Event:
    event = Event(club_id=club_id, title=title, status=status, saved_at=saved_at)
    session.add(event)
    await session.flush()
    return event


async def _conversation(
    session: AsyncSession, event: Event, created_at: datetime
) -> Conversation:
    # 한 트랜잭션 안의 now()는 모두 같아 최근 대화를 가리려면 시각을 직접 넣는다.
    conversation = Conversation(
        event_id=event.id, member_id="mbr_3a71c0", created_at=created_at
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def test_drafts_lists_only_saved_planning_events_newest_first(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    older = await _event(db_session, title="여름 워크샵", saved_at=_at(1))
    newer = await _event(db_session, title="가을 체육대회", saved_at=_at(2))
    await _event(db_session, title="저장 안 함", saved_at=None)
    await _event(
        db_session, title="확정됨", saved_at=_at(3), status=EventStatus.ON_GOING
    )
    for event in (older, newer):
        await _conversation(db_session, event, _at(1))

    response = await api_client.get(DRAFTS_URL, params={"clubId": CLUB_ID})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] is None
    assert [item["title"] for item in body["data"]] == ["가을 체육대회", "여름 워크샵"]
    assert set(body["data"][0]) == {"id", "title", "stage", "savedAt", "conversationId"}
    assert body["data"][0]["savedAt"] == "2026-03-02T00:00:00Z"


async def test_drafts_stage_is_flow_when_steps_exist(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    chat = await _event(db_session, title="대화 중", saved_at=_at(1))
    flow = await _event(db_session, title="흐름 편집 중", saved_at=_at(2))
    for event in (chat, flow):
        await _conversation(db_session, event, _at(1))
    db_session.add(
        Step(
            event_id=flow.id,
            step_order=10,
            phase=StepPhase.PREPARATION,
            name="사전 수요 조사",
            actor=StepActor.MANUAL,
        )
    )
    await db_session.flush()

    response = await api_client.get(DRAFTS_URL, params={"clubId": CLUB_ID})

    assert {item["title"]: item["stage"] for item in response.json()["data"]} == {
        "대화 중": "CHAT",
        "흐름 편집 중": "FLOW",
    }


async def test_drafts_conversation_id_is_latest(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    event = await _event(db_session, title="봄 MT", saved_at=_at(1))
    await _conversation(db_session, event, _at(1, 9))
    latest = await _conversation(db_session, event, _at(1, 10))

    response = await api_client.get(DRAFTS_URL, params={"clubId": CLUB_ID})

    [item] = response.json()["data"]
    assert item["conversationId"] == latest.id


async def test_drafts_skips_event_without_conversation(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    # 대화 없는 계획 한 건 때문에 목록 전체가 실패하면 안 된다.
    with_conversation = await _event(db_session, title="대화 있음", saved_at=_at(1))
    await _conversation(db_session, with_conversation, _at(1))
    await _event(db_session, title="대화 없음", saved_at=_at(2))

    response = await api_client.get(DRAFTS_URL, params={"clubId": CLUB_ID})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["data"]] == ["대화 있음"]

async def test_drafts_excludes_other_clubs(
    api_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    other = Club(name="다른 동아리")
    db_session.add(other)
    await db_session.flush()
    event = await _event(
        db_session, title="남의 행사", saved_at=_at(1), club_id=other.id
    )
    await _conversation(db_session, event, _at(1))

    response = await api_client.get(DRAFTS_URL, params={"clubId": CLUB_ID})

    assert response.json()["data"] == []


async def test_drafts_requires_club_id(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(DRAFTS_URL)

    assert response.status_code == 422
    assert "clubId" in response.json()["error"]["fields"]
