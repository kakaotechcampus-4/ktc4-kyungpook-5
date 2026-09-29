"""계획 시작·임시 저장 목록 API (이슈 #63).

실제 DB에 저장하고 조회한다. 테스트마다 롤백되어 서로 영향을 주지 않는다.
"""

import re

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventStatus, MessageRole
from app.models import Conversation, Event, Message

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CLUB_ID = "clb_3a71c0"  # alembic 시드
EVENTS_URL = "/api/v1/events"
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
