"""Planning snapshots and detail changes share a revision under the event lock."""

import asyncio
from collections.abc import AsyncIterator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import EventStatus, StepActor, StepCode, StepPhase
from app.db import session as db_session
from app.models.chat import Conversation
from app.models.clubs import Member
from app.models.events import Event, Step
from tests.integration.event_seed import add_action, add_event, add_step, owner_with_club

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def test_detail_edits_invalidate_snapshot_and_cancel_blocks_edits(client: TestClient, app_db: None) -> None:
    headers, club = owner_with_club(client)
    event = await add_event(club, status=EventStatus.PLANNING)
    step = await add_step(event, 1)
    action = await add_action(event, step_id=step)
    snapshot_url = f"/api/v1/events/{event}/plan/steps/snapshot"
    snapshot = client.get(snapshot_url, headers=headers).json()["data"]
    assert snapshot["baseRevision"] == 0 and snapshot["steps"][0]["id"] == step

    changed = client.patch(f"/api/v1/steps/{step}", headers=headers,
                           json={"expectedVersion": 1, "deadline": "2026-11-08T00:00:00Z"})
    assert changed.status_code == 200, changed.text
    stale = client.patch(f"/api/v1/events/{event}/plan/steps", headers=headers,
                         json={"expectedRevision": snapshot["baseRevision"], "codes": ["RESEARCH_VENUE"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    snapshot = client.get(snapshot_url, headers=headers).json()["data"]
    assert snapshot["baseRevision"] == 1
    assert snapshot["steps"][0]["deadline"] == "2026-11-08T00:00:00Z"

    changed = client.patch(f"/api/v1/actions/{action}", headers=headers,
                           json={"expectedVersion": 1, "title": "변경된 행동"})
    assert changed.status_code == 200, changed.text
    stale = client.patch(f"/api/v1/events/{event}/plan/steps", headers=headers,
                         json={"expectedRevision": snapshot["baseRevision"], "codes": ["RESEARCH_VENUE"]})
    assert stale.status_code == 409
    snapshot = client.get(snapshot_url, headers=headers).json()["data"]
    assert snapshot["baseRevision"] == 2 and snapshot["steps"][0]["actions"][0]["title"] == "변경된 행동"

    async with db_session.get_sessionmaker()() as session:
        row = await session.get(Event, event)
        row.status = EventStatus.CANCELLING
        await session.commit()
    assert client.patch(f"/api/v1/steps/{step}", headers=headers,
                        json={"expectedVersion": 2, "deadline": None}).status_code == 409
    assert client.patch(f"/api/v1/actions/{action}", headers=headers,
                        json={"expectedVersion": 2, "title": "금지"}).status_code == 409


async def test_snapshot_waits_for_structure_writer_and_returns_consistent_revision(client: TestClient, app_db: None) -> None:
    headers, club = owner_with_club(client)
    event_id = await add_event(club, status=EventStatus.PLANNING)
    await add_step(event_id, 1)
    async with db_session.get_sessionmaker()() as session:
        event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        owner = await session.scalar(select(Member).where(Member.club_id == club))
        pending = asyncio.create_task(asyncio.to_thread(
            client.get, f"/api/v1/events/{event_id}/plan/steps/snapshot", headers=headers
        ))
        await asyncio.sleep(0.2)
        assert not pending.done()
        session.add(Conversation(event_id=event.id, member_id=owner.id, base_revision=1))
        session.add(Step(event_id=event.id, step_order=2, code=StepCode.RESEARCH_VENUE,
                         phase=StepPhase.PREPARATION, name="장소", actor=StepActor.MANUAL))
        await session.commit()
        result = await asyncio.wait_for(pending, timeout=5)
    assert result.status_code == 200, result.text
    snapshot = result.json()["data"]
    assert snapshot["baseRevision"] == 1
    assert [row["code"] for row in snapshot["steps"]] == ["ASSIGN_ROLES", "RESEARCH_VENUE"]


@pytest.mark.parametrize("kind", ["step", "action"])
async def test_cancel_race_rechecks_status_after_waiting_for_event_lock(
    client: TestClient, app_db: None, kind: str
) -> None:
    headers, club = owner_with_club(client)
    event_id = await add_event(club, status=EventStatus.ON_GOING)
    step = await add_step(event_id, 1)
    action = await add_action(event_id, step_id=step)
    path = f"/api/v1/steps/{step}" if kind == "step" else f"/api/v1/actions/{action}"
    body = {"expectedVersion": 1, "deadline": None} if kind == "step" else {"expectedVersion": 1, "title": "금지"}
    async with db_session.get_sessionmaker()() as session:
        event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        pending = asyncio.create_task(asyncio.to_thread(client.patch, path, headers=headers, json=body))
        await asyncio.sleep(0.2)
        assert not pending.done()
        event.status = EventStatus.CANCELLING
        await session.commit()
        result = await asyncio.wait_for(pending, timeout=5)
    assert result.status_code == 409 and result.json()["error"]["code"] == "NOT_EDITABLE"


async def test_structure_save_rechecks_status_after_waiting_for_cancel(
    client: TestClient, app_db: None
) -> None:
    headers, club = owner_with_club(client)
    event_id = await add_event(club, status=EventStatus.PLANNING)
    await add_step(event_id, 1)
    async with db_session.get_sessionmaker()() as session:
        event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        pending = asyncio.create_task(asyncio.to_thread(
            client.patch, f"/api/v1/events/{event_id}/plan/steps", headers=headers,
            json={"expectedRevision": 0, "codes": ["RESEARCH_VENUE"]},
        ))
        await asyncio.sleep(0.2)
        assert not pending.done()
        event.status = EventStatus.CANCELLING
        await session.commit()
        result = await asyncio.wait_for(pending, timeout=5)
    assert result.status_code == 409 and result.json()["error"]["code"] == "EVENT_NOT_PLANNING"
    snapshot = client.get(f"/api/v1/events/{event_id}/plan/steps/snapshot", headers=headers).json()["data"]
    assert snapshot["steps"][0]["code"] == "ASSIGN_ROLES"
