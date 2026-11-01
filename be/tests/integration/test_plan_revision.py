"""계획 편집 버전과 검토 기준 스냅샷 테스트 (#177).

PLANNING 계획이 실제로 바뀔 때만 events.plan_revision이 오르고, 초안 생성 직후의
계획이 plan_reviews에 기준으로 남는지 확인한다. AI 호출은 monkeypatch로 고정한다.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import EventStatus, PlanReviewStatus, StepCode
from app.db import session as db_session
from app.models.events import Event, PlanReview, Step
from app.services import event_service, plan_review_service
from tests.integration.event_seed import add_action, add_event, add_step, owner_with_club
from tests.integration.test_events_planning import (
    _create_event,
    _fake_chat_result,
    _fake_generation_result,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def _revision(event_id: str) -> int:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(Event.plan_revision).where(Event.id == event_id))


async def _review(event_id: str) -> PlanReview | None:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(PlanReview).where(PlanReview.event_id == event_id))


def _patch_chat(monkeypatch: pytest.MonkeyPatch, **conditions) -> None:
    async def fake_chat(request, *, records=None):
        result = _fake_chat_result(**conditions)
        # 두 번째 턴부터는 저장된 상태가 요청의 행사·대화와 같아야 통과한다.
        state = result.next_state.model_copy(
            update={
                "club_id": request.club_id,
                "event_id": request.event_id,
                "conversation_id": request.conversation_id,
            }
        )
        return result.model_copy(update={"next_state": state})

    monkeypatch.setattr("app.ai.chat_planning", fake_chat)


def _chat(client: TestClient, headers: dict, event_id: str, revision: int):
    res = client.post(
        f"/api/v1/events/{event_id}/plan/chat",
        headers=headers,
        json={"messageId": f"m-{revision}", "message": "조건", "baseRevision": revision},
    )
    assert res.status_code == 200, res.text


async def test_초안_생성은_버전을_올리고_기준_스냅샷을_만든다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request):
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/generate", headers=headers, json={"baseRevision": 0}
    )
    assert res.status_code == 200, res.text

    review = await _review(event_id)
    assert await _revision(event_id) == 1
    assert review is not None
    assert review.status == PlanReviewStatus.NOT_REQUESTED
    assert review.generated_revision == 1
    assert [s["code"] for s in review.baseline["steps"]] == ["RESEARCH_VENUE", "COLLECT_FEES"]


async def test_대화로_조건이_바뀌면_버전이_오른다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    _patch_chat(monkeypatch, event_type="MT", headcount=20)
    _chat(client, headers, event_id, 0)
    assert await _revision(event_id) == 1

    _patch_chat(monkeypatch, event_type="MT", headcount=30)
    _chat(client, headers, event_id, 1)
    assert await _revision(event_id) == 2


async def test_조건이_같으면_오르지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    _patch_chat(monkeypatch, event_type="MT", headcount=20)
    _chat(client, headers, event_id, 0)
    _chat(client, headers, event_id, 1)

    assert await _revision(event_id) == 1


async def _planning_event_with_steps(club_id: str) -> tuple[str, str, str]:
    event_id = await add_event(club_id, status=EventStatus.PLANNING)
    step_id = await add_step(event_id, 1, code=StepCode.RESEARCH_VENUE)
    action_id = await add_action(event_id, step_id=step_id)
    return event_id, step_id, action_id


async def test_단계_구성이_바뀌면_버전이_오른다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id, _step_id, _action_id = await _planning_event_with_steps(club_id)

    res = client.patch(
        f"/api/v1/events/{event_id}/plan/steps",
        headers=headers,
        json={"codes": ["RESEARCH_VENUE", "COLLECT_FEES"]},
    )

    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 1


async def test_같은_구성을_저장하면_오르지_않는다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id, _step_id, _action_id = await _planning_event_with_steps(club_id)

    res = client.patch(
        f"/api/v1/events/{event_id}/plan/steps", headers=headers, json={"codes": ["RESEARCH_VENUE"]}
    )

    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 0


async def test_단계_일정이_바뀌면_버전이_오른다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id, step_id, _action_id = await _planning_event_with_steps(club_id)

    res = client.patch(
        f"/api/v1/steps/{step_id}", headers=headers, json={"deadline": "2027-05-01T09:00:00Z"}
    )

    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 1


async def test_같은_일정이면_오르지_않는다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id, step_id, _action_id = await _planning_event_with_steps(club_id)
    body = {"deadline": "2027-05-01T09:00:00Z"}

    client.patch(f"/api/v1/steps/{step_id}", headers=headers, json=body)
    res = client.patch(f"/api/v1/steps/{step_id}", headers=headers, json=body)

    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 1


async def test_행동_세부가_바뀌면_버전이_오른다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id, _step_id, action_id = await _planning_event_with_steps(club_id)

    res = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers, json={"expectedVersion": 1, "amount": 45000}
    )
    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 1

    # 같은 값을 다시 보내면 계획이 바뀐 게 아니다.
    same = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers, json={"expectedVersion": 2, "amount": 45000}
    )
    assert same.status_code == 200, same.text
    assert await _revision(event_id) == 1


async def test_payload만_바뀌어도_버전이_오르고_같은_payload는_오르지_않는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id, _step_id, action_id = await _planning_event_with_steps(club_id)
    body = {"payload": {"channel": "카카오톡"}}

    res = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers, json={"expectedVersion": 1, **body}
    )
    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 1

    same = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers, json={"expectedVersion": 2, **body}
    )
    assert same.status_code == 200, same.text
    assert await _revision(event_id) == 1


async def test_운영_중_수정은_버전을_올리지_않는다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.ON_GOING)
    step_id = await add_step(event_id, 1)

    res = client.patch(
        f"/api/v1/steps/{step_id}", headers=headers, json={"deadline": "2027-05-01T09:00:00Z"}
    )

    assert res.status_code == 200, res.text
    assert await _revision(event_id) == 0


async def test_동시_저장에도_버전을_잃지_않는다(client: TestClient, app_db: None) -> None:
    _headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.PLANNING)
    first_id = await add_step(event_id, 1, code=StepCode.RESEARCH_VENUE)
    second_id = await add_step(event_id, 2, code=StepCode.COLLECT_FEES)

    async def save(step_id: str, deadline: datetime) -> None:
        async with db_session.get_sessionmaker()() as session:
            step = await session.get(Step, step_id)
            await event_service.update_step(
                session, step=step, starts_at=None, deadline=deadline, fields={"deadline"}
            )

    await asyncio.gather(
        save(first_id, datetime(2027, 5, 1, tzinfo=UTC)),
        save(second_id, datetime(2027, 5, 2, tzinfo=UTC)),
    )

    assert await _revision(event_id) == 2


async def test_검토_상태_저장은_events_modified_at을_바꾸지_않는다(
    client: TestClient, app_db: None
) -> None:
    _headers, club_id = owner_with_club(client)
    event_id, _step_id, _action_id = await _planning_event_with_steps(club_id)

    async def modified_at() -> datetime:
        async with db_session.get_sessionmaker()() as session:
            return await session.scalar(select(Event.modified_at).where(Event.id == event_id))

    before = await modified_at()
    async with db_session.get_sessionmaker()() as session:
        await plan_review_service.reset_baseline(session, event_id, 3)
        await session.commit()

    assert await modified_at() == before
    review = await _review(event_id)
    assert review.generated_revision == 3
    assert review.baseline["steps"][0]["code"] == "RESEARCH_VENUE"
