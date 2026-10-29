"""행사 행동(Action) 목록 API 테스트 (#33, #41).

FE가 의존하는 형태 — 봉투, 키 표기, enum 직렬화, 에러 형식 — 와 함께 M1 승인 대기·
L2 확인 요청·처리된 승인 화면이 쓰는 필터·정렬·권한 값을 실제 DB로 확인한다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.enums import ActionStatus, ActionType, MemberRole
from app.db import session as db_session
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


def _walk_keys(value: object):
    """응답 전체에서 dict 키를 모은다. 중첩된 객체·배열도 본다."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _owner_member_id(client: TestClient, headers: dict, club_id: str) -> str:
    rows = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers).json()["data"]
    return rows[0]["id"]


async def _event_with_actions(client: TestClient) -> tuple[dict, str, str, dict]:
    """대표 헤더, clubId, eventId, 행동 id들. 처리된 행동·확인 요청을 골고루 넣는다."""
    headers, club_id = owner_with_club(client)
    owner_id = _owner_member_id(client, headers, club_id)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10, name="입금 확인")
    ids = {
        "pending_late": await add_action(
            event_id, step_id=step_id, title="잔금 송금", type=ActionType.TRANSFER,
            due_date=date(2026, 3, 20),
        ),
        "pending_soon": await add_action(
            event_id, step_id=step_id, title="미납 안내", type=ActionType.EXTERNAL_SEND,
            due_date=date(2026, 3, 12), content="이번 주 금요일까지 입금 부탁드려요.",
        ),
        "pending_undated": await add_action(event_id, step_id=step_id),
        "confirmation": await add_action(
            event_id, title="숙소를 B펜션으로 바꿀까요?", type=ActionType.CONFIRMATION,
            approve_needed=False,
            payload={
                "options": [{"key": "CHANGE_B", "label": "B펜션으로 변경"}],
                "allow_manual": True,
            },
        ),
        "denied_old": await add_action(
            event_id, step_id=step_id, type=ActionType.CONTRACT,
            status=ActionStatus.DENIED, resolved_by=owner_id,
            resolved_at=datetime(2026, 3, 8, tzinfo=UTC),
        ),
        "approved_recent": await add_action(
            event_id, step_id=step_id, type=ActionType.EXPENSE,
            status=ActionStatus.APPROVED, resolved_by=owner_id,
            resolved_at=datetime(2026, 3, 9, tzinfo=UTC),
        ),
    }
    return headers, club_id, event_id, ids


def _url(event_id: str) -> str:
    return f"/api/v1/events/{event_id}/actions"


# --- 응답 계약 ----------------------------------------------------------------


async def test_응답이_data_meta_봉투이고_snake_case가_없다(
    client: TestClient, app_db: None
) -> None:
    headers, _club_id, event_id, _ids = await _event_with_actions(client)

    res = client.get(_url(event_id), headers=headers)

    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {"data", "meta"}
    assert set(body["meta"]) == {"page", "size", "totalCount"}
    assert sorted({key for key in _walk_keys(body) if "_" in key}) == []


async def test_없는_eventId는_404_에러_봉투다(client: TestClient, app_db: None) -> None:
    headers, _club_id = owner_with_club(client)

    res = client.get(_url("evt_없는행사"), headers=headers)

    assert res.status_code == 404
    body = res.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "EVENT_NOT_FOUND"
    assert "detail" not in body


async def test_잘못된_쿼리는_422_에러_봉투로_바뀐다(client: TestClient, app_db: None) -> None:
    headers, _club_id, event_id, _ids = await _event_with_actions(client)

    for params, field in (({"size": 0}, "size"), ({"status": "WAITING"}, "status")):
        res = client.get(_url(event_id), headers=headers, params=params)
        assert res.status_code == 422
        body = res.json()
        assert set(body) == {"error"}
        assert body["error"]["code"] == "VALIDATION_FAILED"
        assert field in body["error"]["fields"]


async def test_토큰이_없으면_401(client: TestClient, app_db: None) -> None:
    _headers, _club_id, event_id, _ids = await _event_with_actions(client)

    assert client.get(_url(event_id)).status_code == 401


# --- 화면별 조회 --------------------------------------------------------------


async def test_M1_승인_대기는_마감_임박_순이고_확인_요청을_뺀다(
    client: TestClient, app_db: None
) -> None:
    headers, _club_id, event_id, ids = await _event_with_actions(client)

    res = client.get(
        _url(event_id),
        headers=headers,
        params={"status": "PENDING", "excludeType": "CONFIRMATION"},
    )

    assert res.status_code == 200, res.text
    assert [a["id"] for a in res.json()["data"]] == [
        ids["pending_soon"],
        ids["pending_late"],
        ids["pending_undated"],
    ]
    assert res.json()["meta"]["totalCount"] == 3
    assert all(a["status"] == "PENDING" for a in res.json()["data"])


async def test_L2_확인_요청은_선택지를_펼쳐_내려준다(
    client: TestClient, app_db: None
) -> None:
    headers, _club_id, event_id, ids = await _event_with_actions(client)

    res = client.get(
        _url(event_id),
        headers=headers,
        params={"status": "PENDING", "type": "CONFIRMATION"},
    )

    [confirmation] = res.json()["data"]
    assert confirmation["id"] == ids["confirmation"]
    assert confirmation["stepId"] is None
    assert confirmation["stepName"] is None
    assert confirmation["options"] == [{"key": "CHANGE_B", "label": "B펜션으로 변경"}]
    assert confirmation["allowManual"] is True


async def test_L2_처리된_승인은_최근_처리_순이고_처리자가_붙는다(
    client: TestClient, app_db: None
) -> None:
    headers, _club_id, event_id, ids = await _event_with_actions(client)

    res = client.get(
        _url(event_id),
        headers=headers,
        params={"status": "APPROVED,DONE,DENIED", "size": 3},
    )

    rows = res.json()["data"]
    assert [a["id"] for a in rows] == [ids["approved_recent"], ids["denied_old"]]
    assert rows[0]["resolvedBy"]["role"] == "OWNER"
    assert rows[0]["stepName"] == "입금 확인"
    assert res.json()["meta"] == {"page": 1, "size": 3, "totalCount": 2}


async def test_승인_대상_본문_content가_내려간다(client: TestClient, app_db: None) -> None:
    headers, _club_id, event_id, ids = await _event_with_actions(client)

    rows = client.get(_url(event_id), headers=headers).json()["data"]

    by_id = {a["id"]: a for a in rows}
    assert by_id[ids["pending_soon"]]["content"] == "이번 주 금요일까지 입금 부탁드려요."
    # 선택지는 확인 요청에만 있다.
    assert by_id[ids["pending_soon"]]["options"] is None


# --- 권한 값 ------------------------------------------------------------------


async def test_운영진만_대기_중인_행동을_처리할_수_있다(
    client: TestClient, app_db: None
) -> None:
    owner_headers, club_id, event_id, ids = await _event_with_actions(client)
    manager_headers = await member_of(client, club_id, MemberRole.MANAGER, "manager")
    member_headers = await member_of(client, club_id, MemberRole.MEMBER, "member")

    def can_approve(headers: dict) -> dict[str, bool]:
        rows = client.get(_url(event_id), headers=headers).json()["data"]
        return {a["id"]: a["canApprove"] for a in rows}

    owner_view = can_approve(owner_headers)
    assert owner_view[ids["pending_soon"]] is True
    assert owner_view[ids["approved_recent"]] is False
    assert can_approve(manager_headers)[ids["pending_soon"]] is True
    assert not any(can_approve(member_headers).values())


async def test_대기와_승인된_행동만_고칠_수_있다(client: TestClient, app_db: None) -> None:
    headers, _club_id, event_id, ids = await _event_with_actions(client)

    rows = client.get(_url(event_id), headers=headers).json()["data"]

    editable = {a["id"]: a["editable"] for a in rows}
    assert editable[ids["pending_soon"]] is True
    assert editable[ids["approved_recent"]] is True
    assert editable[ids["denied_old"]] is False
