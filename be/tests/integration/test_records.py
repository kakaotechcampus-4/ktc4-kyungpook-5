"""동아리 기록 목록 API 테스트 (#42).

FE 자료 탭(RecordsTab)이 쓰는 GET /records?clubId= 가 실제 DB로 동작하는지 확인한다.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.db import session as db_session

pytestmark = [pytest.mark.db, pytest.mark.anyio]

PASSWORD = "PmTest-2027!"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _login(client: TestClient, tag: str) -> dict:
    email = f"{tag}-{uuid.uuid4().hex[:12]}@example.com"
    client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": tag}
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}


def _owner_with_club(client: TestClient) -> tuple[dict, str]:
    headers = _login(client, "rec-owner")
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "기록 테스트 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


def _upload(
    client: TestClient, headers: dict, club_id: str, category: str, file_name: str
) -> str:
    res = client.post(
        "/api/v1/records",
        headers=headers,
        data={"clubId": club_id, "category": category},
        files={"file": (file_name, b"a,b\n1,2\n", "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


async def test_클럽_기록을_목록으로_받는다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, "RULES", "rules.csv")
    _upload(client, headers, club_id, "LEDGER", "ledger.csv")

    res = client.get("/api/v1/records", headers=headers, params={"clubId": club_id})

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 2
    assert body["meta"]["totalCount"] == 2
    assert body["meta"]["page"] == 1


async def test_category로_거를_수_있다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, "RULES", "rules.csv")
    _upload(client, headers, club_id, "LEDGER", "ledger.csv")

    res = client.get(
        "/api/v1/records",
        headers=headers,
        params={"clubId": club_id, "category": "RULES"},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["category"] == "RULES"


async def test_최신순으로_정렬된다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    first_id = _upload(client, headers, club_id, "ETC", "first.csv")
    second_id = _upload(client, headers, club_id, "ETC", "second.csv")

    res = client.get("/api/v1/records", headers=headers, params={"clubId": club_id})

    ids = [row["id"] for row in res.json()["data"]]
    assert ids == [second_id, first_id]


async def test_다른_동아리_기록은_보이지_않는다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, "ETC", "mine.csv")

    other_headers, other_club_id = _owner_with_club(client)
    _upload(client, other_headers, other_club_id, "ETC", "theirs.csv")

    res = client.get("/api/v1/records", headers=headers, params={"clubId": club_id})

    assert res.status_code == 200, res.text
    assert len(res.json()["data"]) == 1


async def test_동아리원이_아니면_목록을_볼_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, "ETC", "mine.csv")

    outsider_headers = _login(client, "rec-outsider")

    res = client.get(
        "/api/v1/records", headers=outsider_headers, params={"clubId": club_id}
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


async def test_원본_다운로드는_같은_동아리만_허용(client: TestClient, app_db: None, tmp_path, monkeypatch) -> None:
    from app.core.config import get_settings
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    headers, club_id = _owner_with_club(client)
    record_id = _upload(client, headers, club_id, "ETC", "minutes.csv")
    response = client.get(f"/api/v1/records/{record_id}/file", headers=headers)
    assert response.status_code == 200
    assert response.content == b"a,b\n1,2\n"
    outsider = _login(client, "rec-download-outsider")
    denied = client.get(f"/api/v1/records/{record_id}/file", headers=outsider)
    assert denied.status_code == 403
