"""영수 내역 기록 API의 응답 계약과 실제 동작 테스트 (#133).

accounting.curl.sh A01~A09가 실제 DB로 끝까지 도는지 확인한다. CSV 파싱은
결정론적 코드이며, 영수증 AI는 테스트에서 고정 응답으로 대체한다.
"""

import uuid
from datetime import date

from app import ai
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
    assert len(body["expenseRows"]) == 2
    assert body["totalAmount"] == 32000
    assert body["errors"] == []
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


def _upload_two_row_csv(client: TestClient, headers: dict, club_id: str) -> str:
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
    return upload.json()["data"]["id"]


async def test_가져오기를_확정할_때_고른_행사가_모든_지출에_연결된다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    event = client.post(
        "/api/v1/events", headers=headers, json={"clubId": club_id, "title": "봄 MT"}
    )
    assert event.status_code == 201, event.text
    event_id = event.json()["data"]["id"]
    import_id = _upload_two_row_csv(client, headers, club_id)

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 1, "eventId": event_id},
    )

    assert confirm.status_code == 200, confirm.text
    expense_ids = set(confirm.json()["data"]["expenseIds"])
    rows = client.get(f"/api/v1/clubs/{club_id}/expenses", headers=headers).json()["data"]
    assert {row["id"]: row["eventId"] for row in rows} == {i: event_id for i in expense_ids}


async def test_가져오기를_행사_없이_확정하면_지출은_행사에_연결되지_않는다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    import_id = _upload_two_row_csv(client, headers, club_id)

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 1, "eventId": None},
    )

    assert confirm.status_code == 200, confirm.text
    rows = client.get(f"/api/v1/clubs/{club_id}/expenses", headers=headers).json()["data"]
    assert [row["eventId"] for row in rows] == [None, None]


async def test_다른_동아리_행사로_확정하면_422이고_지출을_만들지_않는다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    other_token, other_club_id = _owner_with_club(client)
    other_event = client.post(
        "/api/v1/events",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"clubId": other_club_id, "title": "남의 행사"},
    )
    assert other_event.status_code == 201, other_event.text
    import_id = _upload_two_row_csv(client, headers, club_id)

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 1, "eventId": other_event.json()["data"]["id"]},
    )

    assert confirm.status_code == 422, confirm.text
    assert confirm.json()["error"]["code"] == "VALIDATION_FAILED"
    assert client.get(f"/api/v1/clubs/{club_id}/expenses", headers=headers).json()["data"] == []
    detail = client.get(f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}", headers=headers)
    assert detail.json()["data"]["status"] == "NEEDS_REVIEW"


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


async def test_영수증_이미지는_검수_초안을_만들고_수정_후_확정된다(
    client: TestClient, app_db: None, monkeypatch
) -> None:
    async def fake_ocr(request):
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(spent_at=date(2026, 11, 4), merchant=None, amount=1000, category=None, description=None),))
    monkeypatch.setattr(ai, "extract_receipt", fake_ocr)
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
    assert len(body["expenseRows"]) == 1
    import_id = body["id"]
    row_no = body["expenseRows"][0]["rowNo"]

    job = client.get(f"/api/v1/agent-jobs/{body['jobId']}", headers=headers)
    assert job.json()["data"]["kind"] == "RECEIPT_OCR"
    assert job.json()["data"]["status"] == "SUCCEEDED"
    assert job.json()["data"]["result"] == {"receiptImportId": import_id}

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
    assert draft.json()["data"]["expenseRows"][0]["merchant"] == "진짜 가게"

    from app.models.accounting import ReceiptImport, ReceiptImportRow
    async with get_sessionmaker()() as session:
        stored = await session.get(ReceiptImport, import_id)
        row = await session.scalar(select(ReceiptImportRow).where(ReceiptImportRow.receipt_import_id == import_id))
        assert stored.extraction_result['rows'][0]['amount'] == 1000
        assert row.raw_fields['amount'] == 1000 and row.amount == 12345

    confirm = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports/{import_id}/confirm",
        headers=headers,
        json={"expectedVersion": 2},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["data"]["status"] == "CONFIRMED"
    assert len(confirm.json()["data"]["expenseIds"]) == 1


async def test_버전이_다르면_409_VERSION_CONFLICT(
    client: TestClient, app_db: None, monkeypatch
) -> None:
    async def fake_ocr(request):
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(spent_at=date(2026, 11, 4), merchant=None, amount=1000, category=None, description=None),))
    monkeypatch.setattr(ai, "extract_receipt", fake_ocr)
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    upload = client.post(
        f"/api/v1/clubs/{club_id}/receipt-imports",
        headers=headers,
        data={"type": "RECEIPT_IMAGE"},
        files={"file": ("receipt.jpg", b"\xff\xd8\xff\xe0fake", "image/jpeg")},
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


async def test_ocr_failure_retry_and_draft_do_not_create_expense(client, app_db, monkeypatch):
    calls = 0
    async def fake_ocr(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ai.AIConfigError('secret should not appear')
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(spent_at=date(2026, 11, 4), merchant='가게', amount=12000, category=None, description=None),))
    monkeypatch.setattr(ai, 'extract_receipt', fake_ocr)
    token, club_id = _owner_with_club(client); headers = {'Authorization': f'Bearer {token}'}
    base = f'/api/v1/clubs/{club_id}/receipt-imports'
    response = client.post(base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('receipt.jpg', b'\xff\xd8\xff\xe0fake', 'image/jpeg')})
    assert response.status_code == 202 and response.json()['data']['status'] == 'FAILED'
    assert response.json()['data']['error']['reason'] == 'OCR_NOT_CONFIGURED'
    assert 'secret' not in response.text
    import_id = response.json()['data']['id']
    retry = client.post(f'{base}/{import_id}/retry', headers=headers)
    assert retry.status_code == 200 and retry.json()['data']['status'] == 'NEEDS_REVIEW'
    row = retry.json()['data']['expenseRows'][0]
    assert row['spentAt'] == '2026-11-03T15:00:00Z' and row['amount'] == 12000
    assert row['confirmedExpenseId'] is None
    assert client.get(f'/api/v1/clubs/{club_id}/expenses', headers=headers).json()['data'] == []
    assert client.post(f'{base}/{import_id}/confirm', headers=headers, json={'expectedVersion': 1}).status_code == 200
    assert len(client.get(f'/api/v1/clubs/{club_id}/expenses', headers=headers).json()['data']) == 1


async def test_ocr_rejects_wrong_mime_and_empty_result(client, app_db, monkeypatch):
    async def empty(request): return ai.ExtractReceiptResult(rows=())
    monkeypatch.setattr(ai, 'extract_receipt', empty)
    token, club_id = _owner_with_club(client); headers = {'Authorization': f'Bearer {token}'}
    base = f'/api/v1/clubs/{club_id}/receipt-imports'
    assert client.post(base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('x.png', b'bad', 'image/png')}).status_code == 422
    response = client.post(base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('x.jpg', b'\xff\xd8\xff\xe0fake', 'image/jpeg')})
    assert response.json()['data']['status'] == 'FAILED'
    assert response.json()['data']['error']['reason'] == 'OCR_NO_READABLE_RECEIPT'


async def test_ocr_wait_releases_db_and_stale_retry_discards_late_response(client, app_db, monkeypatch):
    import asyncio
    import threading
    from datetime import UTC, datetime, timedelta
    from app.models.accounting import ReceiptImport
    from app.models.agent import AgentJob
    started, release = threading.Event(), threading.Event()
    calls = 0
    async def fake_ocr(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set(); await asyncio.to_thread(release.wait, 10)
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(spent_at=date(2026,11,4), merchant=f'가게{calls}', amount=1000, category=None, description=None),))
    monkeypatch.setattr(ai, 'extract_receipt', fake_ocr)
    token, club_id = _owner_with_club(client); headers = {'Authorization': f'Bearer {token}'}
    base = f'/api/v1/clubs/{club_id}/receipt-imports'
    pending = asyncio.create_task(asyncio.to_thread(client.post, base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('x.jpg', b'\xff\xd8\xff\xe0fake', 'image/jpeg')}))
    assert await asyncio.to_thread(started.wait, 5)
    try:
        async with get_sessionmaker()() as session:
            item = await session.scalar(select(ReceiptImport).where(ReceiptImport.club_id == club_id).with_for_update())
            assert item.status.value == 'PROCESSING'
            import_id = item.id
            job = await session.get(AgentJob, item.job_id)
            job.started_at = datetime.now(UTC) - timedelta(minutes=4)
            await session.commit()
        retry = await asyncio.to_thread(client.post, f'{base}/{import_id}/retry', headers=headers)
        assert retry.status_code == 200 and retry.json()['data']['status'] == 'NEEDS_REVIEW'
    finally:
        release.set()
    assert (await pending).status_code == 202
    rows = client.get(f'{base}/{import_id}', headers=headers).json()['data']['expenseRows']
    assert len(rows) == 1 and rows[0]['merchant'] == '가게2'


async def test_concurrent_ocr_confirm_creates_one_expense(client, app_db, monkeypatch):
    import asyncio
    async def fake_ocr(request):
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(spent_at=date(2026, 11, 4), merchant='가게', amount=1000, category=None, description=None),))
    monkeypatch.setattr(ai, 'extract_receipt', fake_ocr)
    token, club_id = _owner_with_club(client); headers = {'Authorization': f'Bearer {token}'}
    base = f'/api/v1/clubs/{club_id}/receipt-imports'
    case = client.post(base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('x.jpg', b'\xff\xd8\xff\xe0fake', 'image/jpeg')}).json()['data']
    path = f"{base}/{case['id']}/confirm"
    responses = await asyncio.gather(*(asyncio.to_thread(client.post, path, headers=headers, json={'expectedVersion':1}) for _ in range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(client.get(f'/api/v1/clubs/{club_id}/expenses', headers=headers).json()['data']) == 1


@pytest.mark.parametrize('field,value', [('amount', 2147483648), ('merchant', 'x' * 201), ('category', 'x' * 51)])
async def test_ocr_oversized_result_fails_without_stuck_processing(client, app_db, monkeypatch, field, value):
    values = dict(spent_at=date(2026, 11, 4), merchant='가게', amount=1000, category=None, description=None)
    values[field] = value
    async def fake_ocr(request):
        return ai.ExtractReceiptResult(rows=(ai.ExtractedReceiptRow(**values),))
    monkeypatch.setattr(ai, 'extract_receipt', fake_ocr)
    token, club_id = _owner_with_club(client)
    headers = {'Authorization': f'Bearer {token}'}
    base = f'/api/v1/clubs/{club_id}/receipt-imports'
    upload = client.post(base, headers=headers, data={'type':'RECEIPT_IMAGE'}, files={'file':('receipt.jpg', b'\xff\xd8\xff\xe0fake', 'image/jpeg')})
    assert upload.status_code == 202, upload.text
    item = upload.json()['data']
    assert item['status'] == 'FAILED' and item['error']['reason'] == 'OCR_INVALID_RESULT'
    assert client.get(f"{base}/{item['id']}", headers=headers).json()['data']['status'] == 'FAILED'
    assert client.get(f'/api/v1/clubs/{club_id}/expenses', headers=headers).json()['data'] == []
