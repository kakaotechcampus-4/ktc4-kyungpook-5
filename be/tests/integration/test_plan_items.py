"""단계·Action 세부 수정 API 테스트 (#106 ④).

FE 세부 수정 모달이 의존하는 것 — 어떤 밭을 그릴지 정하는 payload, 잠금 판정인
editable, 보낸 키만 덮는 부분 수정, 금액의 Event 파생 — 을 실제 DB로 확인한다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import ActionStatus, ActionType, MemberRole, StepCode
from app.db import session as db_session
from app.models.events import Event
from tests.integration.event_seed import (
    add_action,
    add_event,
    add_step,
    member_of,
    owner_with_club,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def _fee_of(event_id: str) -> int | None:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(Event.fee_per_person).where(Event.id == event_id))


async def test_단계_목록은_code와_editable과_붙은_행동을_함께_준다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1, code=StepCode.COLLECT_FEES, name="참가비 수금")
    await add_action(
        event_id,
        step_id=step_id,
        type=ActionType.NOTICE,
        payload={"channel": "단톡방"},
    )

    res = client.get(f"/api/v1/events/{event_id}/plan/steps", headers=headers)
    assert res.status_code == 200, res.text
    step = res.json()["data"][0]

    # FE가 이름 문자열로 단계를 되찾지 않아도 되도록 code를 함께 준다.
    assert step["code"] == "COLLECT_FEES"
    assert step["editable"] is True
    action = step["actions"][0]
    assert action["editable"] is True
    # 해당 없는 키는 아예 빠진다 — "값이 비었다"와 구분되어야 한다.
    assert action["payload"] == {"channel": "단톡방"}


async def test_확인_요청의_payload는_선택지라_세부_수정_대상이_아니다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1)
    await add_action(
        event_id,
        step_id=step_id,
        type=ActionType.CONFIRMATION,
        payload={"options": [{"key": "ok", "label": "확인"}], "allow_manual": False},
    )

    res = client.get(f"/api/v1/events/{event_id}/plan/steps", headers=headers)
    assert res.json()["data"][0]["actions"][0]["payload"] is None


async def test_단계_일정을_고치면_보낸_밭만_바뀐다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1)

    first = client.patch(
        f"/api/v1/steps/{step_id}",
        headers=headers,
        json={"startsAt": "2026-11-05T00:00:00+09:00", "deadline": "2026-11-08T00:00:00+09:00"},
    )
    assert first.status_code == 200, first.text

    # deadline만 비운다. startsAt은 보내지 않았으므로 그대로 남아야 한다.
    second = client.patch(f"/api/v1/steps/{step_id}", headers=headers, json={"deadline": None})
    assert second.status_code == 200, second.text
    data = second.json()["data"]
    assert data["startsAt"] is not None
    assert data["deadline"] is None


async def test_끝난_단계는_고칠_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1, completed_at=datetime.now(UTC))

    res = client.get(f"/api/v1/events/{event_id}/plan/steps", headers=headers)
    assert res.json()["data"][0]["editable"] is False

    denied = client.patch(f"/api/v1/steps/{step_id}", headers=headers, json={"deadline": None})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "NOT_EDITABLE"


async def test_payload는_보낸_키만_덮고_나머지는_남는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1)
    action_id = await add_action(
        event_id,
        step_id=step_id,
        type=ActionType.NOTICE,
        payload={"channel": "단톡방", "audience": "전체 회원"},
    )

    res = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers, json={"payload": {"audience": "신입생"}}
    )
    assert res.status_code == 200, res.text
    payload = res.json()["data"]["actions"][0]["payload"]
    assert payload == {"channel": "단톡방", "audience": "신입생"}


async def test_수금_금액을_고치면_행사_참가비가_따라_바뀐다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1, code=StepCode.COLLECT_FEES)
    action_id = await add_action(event_id, step_id=step_id, type=ActionType.NOTICE)

    res = client.patch(f"/api/v1/actions/{action_id}", headers=headers, json={"amount": 45000})
    assert res.status_code == 200, res.text
    assert await _fee_of(event_id) == 45000


async def test_예약_계약금은_행사로_올라가지_않는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1, code=StepCode.BOOK_VENUE)
    action_id = await add_action(event_id, step_id=step_id, type=ActionType.CONTRACT)

    client.patch(f"/api/v1/actions/{action_id}", headers=headers, json={"amount": 300000})
    assert await _fee_of(event_id) is None


async def test_승인된_행동을_고치면_다시_승인_대기가_된다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1)
    action_id = await add_action(
        event_id, step_id=step_id, status=ActionStatus.APPROVED, resolved_at=datetime.now(UTC)
    )

    res = client.patch(f"/api/v1/actions/{action_id}", headers=headers, json={"title": "고친 제목"})
    assert res.status_code == 200, res.text

    steps = client.get(f"/api/v1/events/{event_id}/plan/steps", headers=headers)
    action = steps.json()["data"][0]["actions"][0]
    assert action["title"] == "고친 제목"
    assert action["editable"] is True


async def test_일반_동아리원은_세부를_고칠_수_없다(
    client: TestClient, app_db: None
) -> None:
    _owner, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 1)
    member = await member_of(client, club_id, MemberRole.MEMBER)

    res = client.patch(f"/api/v1/steps/{step_id}", headers=member, json={"deadline": None})
    assert res.status_code == 403


async def test_없는_단계와_행동은_404다(client: TestClient, app_db: None) -> None:
    headers, _club_id = owner_with_club(client)
    assert client.patch("/api/v1/steps/stp_none", headers=headers, json={}).status_code == 404
    assert client.patch("/api/v1/actions/act_none", headers=headers, json={}).status_code == 404
