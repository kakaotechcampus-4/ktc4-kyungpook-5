"""한 번 넣으면 고칠 수 없던 지출의 수정·삭제 API 테스트 (#213 4단계)."""

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import MemberRole
from app.db import session as db_session
from app.models.accounting import ReceiptImportRow
from tests.integration.event_seed import add_event, member_of, owner_with_club

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None, tmp_path,
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    yield
    await db_session.get_engine().dispose()


# --- 지출 ------------------------------------------------------------------


def _expense(client: TestClient, headers: dict, club_id: str, **fields) -> dict:
    body = {
        "spentAt": "2026-10-11T09:00:00Z",
        "merchant": "테스트 매장",
        "amount": 18000,
        "description": "회의 간식",
        **fields,
    }
    res = client.post(f"/api/v1/clubs/{club_id}/expenses", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()["data"]


def _patch_expense(client: TestClient, headers: dict, club_id: str, expense_id: str, body: dict):
    return client.patch(
        f"/api/v1/clubs/{club_id}/expenses/{expense_id}", headers=headers, json=body
    )


async def test_지출을_고치면_보낸_필드만_바뀌고_version이_오른다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client, "exp-edit")
    expense = _expense(client, headers, club_id)

    res = _patch_expense(
        client, headers, club_id, expense["id"],
        {"expectedVersion": 1, "amount": 21000, "description": None},
    )

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["amount"] == 21000
    assert data["description"] is None
    assert data["merchant"] == "테스트 매장"
    assert data["version"] == 2
    detail = client.get(f"/api/v1/clubs/{club_id}/expenses/{expense['id']}", headers=headers)
    assert detail.json()["data"] == data


async def test_본_적_없는_버전의_지출은_고칠_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-version")
    expense = _expense(client, headers, club_id)
    first = _patch_expense(client, headers, club_id, expense["id"], {"expectedVersion": 1, "amount": 1})
    assert first.status_code == 200, first.text

    stale = _patch_expense(client, headers, club_id, expense["id"], {"expectedVersion": 1, "amount": 2})

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_지출일과_금액은_비울_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-required")
    expense = _expense(client, headers, club_id)

    res = _patch_expense(
        client, headers, club_id, expense["id"],
        {"expectedVersion": 1, "spentAt": None, "amount": None},
    )

    assert res.status_code == 422
    assert set(res.json()["error"]["fields"]) == {"spentAt", "amount"}


async def test_다른_동아리의_지출은_고치거나_지울_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-owner")
    other_headers, other_club_id = owner_with_club(client, "exp-other")
    expense = _expense(client, other_headers, other_club_id)

    patched = _patch_expense(client, headers, club_id, expense["id"], {"expectedVersion": 1, "amount": 1})
    deleted = client.delete(f"/api/v1/clubs/{club_id}/expenses/{expense['id']}", headers=headers)

    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "EXPENSE_NOT_FOUND"
    assert deleted.status_code == 404


async def test_지출은_같은_동아리_행사에만_연결된다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-event")
    _other_headers, other_club_id = owner_with_club(client, "exp-event-other")
    own_event = await add_event(club_id)
    other_event = await add_event(other_club_id)

    created = client.post(
        f"/api/v1/clubs/{club_id}/expenses",
        headers=headers,
        json={"spentAt": "2026-10-11T09:00:00Z", "amount": 1000, "eventId": other_event},
    )
    expense = _expense(client, headers, club_id, eventId=own_event)
    patched = _patch_expense(
        client, headers, club_id, expense["id"], {"expectedVersion": 1, "eventId": other_event}
    )

    assert created.status_code == 422
    assert "eventId" in created.json()["error"]["fields"]
    assert patched.status_code == 422
    assert "eventId" in patched.json()["error"]["fields"]
    assert expense["eventId"] == own_event
    unlinked = _patch_expense(client, headers, club_id, expense["id"], {"expectedVersion": 1, "eventId": None})
    assert unlinked.json()["data"]["eventId"] is None


async def test_바꾼_것이_없으면_version이_그대로다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-noop")
    expense = _expense(client, headers, club_id)

    res = _patch_expense(client, headers, club_id, expense["id"], {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    assert res.json()["data"] == expense


async def test_사용처와_분류가_컬럼보다_길면_422다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client, "exp-length")
    expense = _expense(client, headers, club_id)

    created = client.post(
        f"/api/v1/clubs/{club_id}/expenses",
        headers=headers,
        json={"spentAt": "2026-10-11T09:00:00Z", "amount": 1000, "merchant": "가" * 201},
    )
    patched = _patch_expense(
        client, headers, club_id, expense["id"], {"expectedVersion": 1, "category": "가" * 51}
    )

    assert created.status_code == 422
    assert patched.status_code == 422
    assert patched.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_운영진이_아닌_동아리원은_지출을_고치거나_지울_수_없다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client, "exp-role")
    member = await member_of(client, club_id, MemberRole.MEMBER, "exp-member")
    expense = _expense(client, headers, club_id)

    patched = _patch_expense(client, member, club_id, expense["id"], {"expectedVersion": 1, "amount": 1})
    deleted = client.delete(f"/api/v1/clubs/{club_id}/expenses/{expense['id']}", headers=member)

    assert patched.status_code == 403
    assert deleted.status_code == 403


async def test_지출을_지우면_조회되지_않고_가져오기_행의_연결이_비워진다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client, "exp-delete")
    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "EXPENSE_CSV"},
        files={"file": ("expense.csv", b"date,merchant,amount\n2026-10-01,Mart A,15000\n", "text/csv")},
    )
    assert upload.status_code == 202, upload.text
    import_id = upload.json()["data"]["id"]
    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 1},
    )
    [expense_id] = confirm.json()["data"]["expenseIds"]

    res = client.delete(f"/api/v1/clubs/{club_id}/expenses/{expense_id}", headers=headers)

    assert res.status_code == 204
    assert res.content == b""
    detail = client.get(f"/api/v1/clubs/{club_id}/expenses/{expense_id}", headers=headers)
    assert detail.status_code == 404
    async with db_session.get_sessionmaker()() as session:
        row = await session.scalar(
            select(ReceiptImportRow).where(ReceiptImportRow.receipt_import_id == import_id)
        )
    assert row is not None
    assert row.confirmed_expense_id is None
