"""행사 목록·상세·단계 조회 API 테스트 (#41, #92).

M1·L1 카드, L2 헤더·진행 상황, P2 단계 묶음이 읽는 값을 실제 DB로 확인한다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    MemberRole,
    StepCode,
    StepPhase,
)
from app.db import session as db_session
from app.services.event_service import today_kst
from tests.integration.event_seed import (
    add_action,
    add_event,
    add_step,
    member_of,
    owner_with_club,
    signup_and_login,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]

EVENTS_URL = "/api/v1/events"
DONE_AT = datetime(2026, 3, 1, tzinfo=UTC)


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


# --- 목록 -------------------------------------------------------------------


async def test_토큰이_없으면_401(client: TestClient, app_db: None) -> None:
    _headers, club_id = owner_with_club(client)

    res = client.get(EVENTS_URL, params={"clubId": club_id})

    assert res.status_code == 401


async def test_clubId가_없으면_422(client: TestClient, app_db: None) -> None:
    headers, _club_id = owner_with_club(client)

    res = client.get(EVENTS_URL, headers=headers)

    assert res.status_code == 422
    assert "clubId" in res.json()["error"]["fields"]


async def test_동아리원이_아니면_목록을_볼_수_없다(client: TestClient, app_db: None) -> None:
    _headers, club_id = owner_with_club(client)
    _account_id, outsider = signup_and_login(client, "outsider")

    res = client.get(EVENTS_URL, headers=outsider, params={"clubId": club_id})

    assert res.status_code == 403


async def test_시작일이_가까운_순이고_날짜_없는_행사는_뒤로_간다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    today = today_kst()
    undated = await add_event(club_id, title="날짜 미정")
    later = await add_event(club_id, title="나중", start_date=today + timedelta(days=30))
    sooner = await add_event(club_id, title="먼저", start_date=today + timedelta(days=3))
    _other_headers, other_club = owner_with_club(client, "other-owner")
    await add_event(other_club, title="다른 동아리")

    res = client.get(EVENTS_URL, headers=headers, params={"clubId": club_id})

    assert res.status_code == 200, res.text
    assert [e["id"] for e in res.json()["data"]] == [sooner, later, undated]
    assert res.json()["meta"] == {"page": 1, "size": 20, "totalCount": 3}


async def test_status와_페이지로_거른다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    today = today_kst()
    for days in (1, 2, 3):
        await add_event(club_id, start_date=today + timedelta(days=days))
    await add_event(club_id, status=EventStatus.PLANNING)

    res = client.get(
        EVENTS_URL,
        headers=headers,
        params={"clubId": club_id, "status": "ON_GOING", "page": 2, "size": 2},
    )

    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 1
    assert res.json()["data"][0]["status"] == "ON_GOING"
    assert res.json()["meta"]["totalCount"] == 3


async def test_카드에_D_day_진행_단계_승인_대기_건수가_계산된다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(
        club_id,
        start_date=today_kst() + timedelta(days=11),
        location="가평 펜션",
        expected_headcount=32,
    )
    await add_step(event_id, 10, name="사전 조사", completed_at=DONE_AT)
    current = await add_step(event_id, 20, name="입금 확인")
    await add_step(event_id, 30, name="사전 안내")
    await add_action(event_id, step_id=current)
    await add_action(event_id, step_id=current, type=ActionType.TRANSFER)
    # 확인 요청과 이미 처리된 행동은 승인 대기로 세지 않는다.
    await add_action(event_id, type=ActionType.CONFIRMATION, approve_needed=False)
    await add_action(event_id, step_id=current, status=ActionStatus.DONE)

    res = client.get(EVENTS_URL, headers=headers, params={"clubId": club_id})

    card = res.json()["data"][0]
    assert card["dday"] == 11
    assert card["location"] == "가평 펜션"
    assert card["headcount"] == 32
    assert card["currentStepName"] == "입금 확인"
    assert card["stepProgress"] == [
        {"stepOrder": 10, "state": "DONE"},
        {"stepOrder": 20, "state": "CURRENT"},
        {"stepOrder": 30, "state": "TODO"},
    ]
    assert card["pendingApprovalCount"] == 2
    assert card["payment"] is None
    assert card["budget"] is None


async def test_단계가_없는_행사는_진행_정보가_비어_있다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    await add_event(club_id, status=EventStatus.PLANNING)

    card = client.get(EVENTS_URL, headers=headers, params={"clubId": club_id}).json()[
        "data"
    ][0]

    assert card["currentStepName"] is None
    assert card["stepProgress"] == []
    assert card["dday"] is None
    assert card["pendingApprovalCount"] == 0


async def test_인원은_컬럼명이_아닌_headcount로_나간다(
    client: TestClient, app_db: None
) -> None:
    """FE 명세 v1이 expectedHeadcount를 headcount로 통일했다 (#92)."""
    headers, club_id = owner_with_club(client)
    await add_event(club_id, expected_headcount=10)

    card = client.get(EVENTS_URL, headers=headers, params={"clubId": club_id}).json()[
        "data"
    ][0]

    assert "location" in card
    assert card["headcount"] == 10
    assert "expectedHeadcount" not in card


# --- 상세 -------------------------------------------------------------------


async def test_상세는_현재_단계를_id까지_내려준다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, title="2026 봄 MT", expected_headcount=32)
    await add_step(event_id, 10, completed_at=DONE_AT)
    current = await add_step(event_id, 20, name="입금 확인")

    res = client.get(f"{EVENTS_URL}/{event_id}", headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["title"] == "2026 봄 MT"
    assert body["data"]["headcount"] == 32
    assert body["data"]["currentStep"] == {
        "id": current,
        "stepOrder": 20,
        "name": "입금 확인",
    }


async def test_모든_단계를_마치면_현재_단계가_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.COMPLETE)
    await add_step(event_id, 10, completed_at=DONE_AT)

    res = client.get(f"{EVENTS_URL}/{event_id}", headers=headers)

    assert res.json()["data"]["currentStep"] is None


async def test_없는_행사는_404_에러_봉투다(client: TestClient, app_db: None) -> None:
    headers, _club_id = owner_with_club(client)

    res = client.get(f"{EVENTS_URL}/evt_없는행사", headers=headers)

    assert res.status_code == 404
    body = res.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "EVENT_NOT_FOUND"


async def test_다른_동아리_행사는_볼_수_없다(client: TestClient, app_db: None) -> None:
    _headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    other_headers, _other_club = owner_with_club(client, "other-owner")

    for path in ("", "/steps", "/actions"):
        res = client.get(f"{EVENTS_URL}/{event_id}{path}", headers=other_headers)
        assert res.status_code == 403, path


async def test_상세_경로가_생겨도_drafts는_그대로_동작한다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)

    res = client.get(f"{EVENTS_URL}/drafts", headers=headers, params={"clubId": club_id})

    assert res.status_code == 200, res.text


# --- 단계 -------------------------------------------------------------------


async def test_단계는_묶음과_한_일_남은_일을_함께_내려준다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    first = await add_step(event_id, 10, completed_at=DONE_AT)
    second = await add_step(
        event_id, 20, code=StepCode.COLLECT_FEES, phase=StepPhase.RECRUITING
    )
    done = await add_action(event_id, step_id=second, status=ActionStatus.DONE)
    pending = await add_action(event_id, step_id=second)
    approved = await add_action(event_id, step_id=second, status=ActionStatus.APPROVED)
    await add_action(event_id, step_id=second, status=ActionStatus.DENIED)
    # 단계에 묶이지 않은 확인 요청은 어느 단계에도 들어가지 않는다.
    await add_action(event_id, type=ActionType.CONFIRMATION, approve_needed=False)

    res = client.get(f"{EVENTS_URL}/{event_id}/steps", headers=headers)

    assert res.status_code == 200, res.text
    steps = res.json()["data"]
    assert [s["id"] for s in steps] == [first, second]
    assert [s["state"] for s in steps] == ["DONE", "CURRENT"]
    assert steps[0]["totalActionCount"] == 0

    step = steps[1]
    assert step["code"] == "COLLECT_FEES"
    assert step["phase"] == "RECRUITING"
    assert step["completedCount"] == 1
    assert step["totalActionCount"] == 4
    assert [a["id"] for a in step["doneActions"]] == [done]
    assert {a["id"] for a in step["remainingActions"]} == {pending, approved}
    assert all("approveNeeded" in a for a in step["remainingActions"])


async def test_운영진은_보고_일반_동아리원은_볼_수_없다(
    client: TestClient, app_db: None
) -> None:
    """서비스 이용 대상은 대표·운영진이다(SERVICE_ROLES). 일반 동아리원은 403이다."""
    _headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    await add_step(event_id, 10)
    manager_headers = await member_of(client, club_id, MemberRole.MANAGER, "manager")
    member_headers = await member_of(client, club_id, MemberRole.MEMBER, "member")

    for url, params in (
        (EVENTS_URL, {"clubId": club_id}),
        (f"{EVENTS_URL}/{event_id}", None),
        (f"{EVENTS_URL}/{event_id}/steps", None),
        (f"{EVENTS_URL}/{event_id}/actions", None),
    ):
        manager = client.get(url, headers=manager_headers, params=params)
        member = client.get(url, headers=member_headers, params=params)
        assert manager.status_code == 200, (url, manager.text)
        assert member.status_code == 403, (url, member.text)
