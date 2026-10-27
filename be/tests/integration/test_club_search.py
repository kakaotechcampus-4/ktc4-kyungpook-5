"""동아리 검색 API 테스트 (#189)."""

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


async def test_로그인_없이도_이름_일부로_찾을_수_있다(client: TestClient, app_db: None) -> None:
    headers = _login(client, "search-owner")
    unique = uuid.uuid4().hex[:8]
    club_name = f"검색용 동아리 {unique}"
    club = client.post(
        "/api/v1/clubs", headers=headers, json={"name": club_name, "category": "ACADEMIC"}
    )
    assert club.status_code == 201, club.text

    res = client.get("/api/v1/clubs", params={"query": unique})

    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["name"] == club_name
    assert rows[0]["field"] == "학술"
    assert rows[0]["executiveCount"] == 1
    assert rows[0]["ownerName"]


async def test_결과_없으면_빈_배열(client: TestClient, app_db: None) -> None:
    res = client.get(
        "/api/v1/clubs", params={"query": f"존재하지않는동아리{uuid.uuid4().hex}"}
    )

    assert res.status_code == 200, res.text
    assert res.json()["data"] == []


async def test_빈_검색어는_422(client: TestClient, app_db: None) -> None:
    res = client.get("/api/v1/clubs", params={"query": ""})

    assert res.status_code == 422, res.text
