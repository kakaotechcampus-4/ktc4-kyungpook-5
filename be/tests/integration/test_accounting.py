"""영수 내역 기록 API의 응답 계약과 실제 동작 테스트 (#133).

accounting.curl.sh A01~A09가 실제 DB로 끝까지 도는지 확인한다. CSV 파싱은
결정론적 코드, 영수증 이미지는 더미 OCR(services/receipt_ocr_stub.py)이다.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import MemberRole
from app.db import session as db_session
from app.db.session import get_sessionmaker
from app.models.auth import Account
from app.models.clubs import Member

pytestmark = [pytest.mark.db, pytest.mark.anyio]

PASSWORD = "PmTest-2027!"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _unique_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:12]}@example.com"


def _owner_with_club(client: TestClient) -> tuple[str, str]:
    """(accessToken, clubId)를 가진 OWNER 계정을 만든다."""
    email = _unique_email("acct-owner")
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "name": "회계 테스트"},
    )
    assert signup.status_code == 201, signup.text
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    access_token = login.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {access_token}"}
    club = client.post(
        "/api/v1/clubs", headers=headers, json={"name": "회계 테스트 동아리"}
    )
    assert club.status_code == 201, club.text
    return access_token, club.json()["data"]["id"]


async def test_직접_입력하면_바로_CONFIRMED_의미로_저장된다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    res = client.post(
        f"/api/v1/clubs/{club_id}/expenses",
        headers=headers,
        json={
            "description": "회의 간식",
            "merchant": "테스트 매장",
            "spentAt": "2026-10-11T09:00:00Z",
            "amount": 18000,
            "currency": "KRW",
        },
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["source"] == "MANUAL"
    assert body["data"]["amount"] == 18000


async def test_CSV_업로드부터_확정까지(client: TestClient, app_db: None) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    csv_bytes = (
        b"date,merchant,amount,description\n"
        b"2026-10-01,Mart A,15000,Snacks\n"
        b"2026-10-02,Store B,17000,Drinks\n"
    )

    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "EXPENSE_CSV"},
        files={"file": ("expense.csv", csv_bytes, "text/csv")},
    )
    assert upload.status_code == 202, upload.text
    body = upload.json()["data"]
    assert body["status"] == "NEEDS_REVIEW"
    assert len(body["rows"]) == 2
    import_id = body["id"]

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 1},
    )
    assert confirm.status_code == 200, confirm.text
    expense_ids = confirm.json()["data"]["expenseIds"]
    assert len(expense_ids) == 2

    expenses = client.get(f"/api/v1/clubs/{club_id}/expenses", headers=headers)
    sources = {row["source"] for row in expenses.json()["data"]}
    assert sources == {"CSV_IMPORT"}


async def test_잘못된_CSV는_FAILED_상태이고_확정을_거부한다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    bad_csv = b"foo,bar\n1,2\n"

    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "EXPENSE_CSV"},
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert upload.status_code == 202
    body = upload.json()["data"]
    assert body["status"] == "FAILED"
    assert body["error"]["reason"] == "COLUMN_MISMATCH"

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{body['id']}/confirm",
        headers=headers,
        json={"expectedVersion": 1},
    )
    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "IMPORT_NOT_READY"


async def test_영수증_이미지는_더미_OCR_초안을_만들고_수정_후_확정된다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "RECEIPT_IMAGE"},
        files={"file": ("receipt.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")},
    )
    assert upload.status_code == 202, upload.text
    body = upload.json()["data"]
    assert body["status"] == "NEEDS_REVIEW"
    assert len(body["rows"]) == 1
    import_id = body["id"]
    row_no = body["rows"][0]["rowNo"]

    draft = client.patch(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/draft",
        headers=headers,
        json={
            "expectedVersion": 1,
            "expenseRows": [
                {"rowNo": row_no, "merchant": "진짜 가게", "amount": 12345}
            ],
        },
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["data"]["version"] == 2
    assert draft.json()["data"]["rows"][0]["merchant"] == "진짜 가게"

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 2},
    )
    assert confirm.status_code == 200, confirm.text
    assert len(confirm.json()["data"]["expenseIds"]) == 1


async def test_버전이_다르면_409_VERSION_CONFLICT(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "RECEIPT_IMAGE"},
        files={"file": ("receipt.jpg", b"fake-bytes", "image/jpeg")},
    )
    import_id = upload.json()["data"]["id"]

    res = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 999},
    )

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_MEMBER_역할은_지출을_등록할_수_없다(
    client: TestClient, app_db: None
) -> None:
    _owner_token, club_id = _owner_with_club(client)

    # 초대 수락 흐름(더미 메일 발송)은 test_auth_clubs.py에서 이미 검증했으므로,
    # 여기서는 역할 검증만 보면 되도록 서비스 계층으로 바로 MEMBER를 만든다.
    member_email = _unique_email("acct-member")
    client.post(
        "/api/v1/auth/signup",
        json={"email": member_email, "password": PASSWORD, "name": "일반 회원"},
    )
    async with get_sessionmaker()() as session:
        account = await session.scalar(select(Account).where(Account.email == member_email))
        session.add(
            Member(
                club_id=club_id,
                account_id=account.id,
                name="일반 회원",
                role=MemberRole.MEMBER,
            )
        )
        await session.commit()

    member_login = client.post(
        "/api/v1/auth/login", json={"email": member_email, "password": PASSWORD}
    )
    member_headers = {
        "Authorization": f"Bearer {member_login.json()['data']['accessToken']}"
    }

    res = client.post(
        f"/api/v1/clubs/{club_id}/expenses",
        headers=member_headers,
        json={"spentAt": "2026-10-11T09:00:00Z", "amount": 1000},
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"
