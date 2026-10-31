"""동아리원 목록 API 테스트 (#188)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.core.enums import MemberRole, MemberStatus
from app.db import session as db_session
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


def _login(client: TestClient, tag: str) -> dict:
    email = f"{tag}-{uuid.uuid4().hex[:12]}@example.com"
    client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": tag}
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}


def _owner_with_club(client: TestClient) -> tuple[dict, str]:
    headers = _login(client, "mem-owner")
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "명단 테스트 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


async def test_대표는_임원_JOINED로_보인다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)

    res = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers)

    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 1
    assert rows[0]["group"] == "임원"
    assert rows[0]["subtitle"] == "대표"
    assert rows[0]["account"] == "JOINED"
    assert rows[0]["accountAt"] is not None


async def test_초대한_사람은_이메일로_INVITED로_보인다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    client.post(
        f"/api/v1/clubs/{club_id}/invitations",
        headers=headers,
        json={"email": "new-officer@example.com", "role": "MANAGER"},
    )

    res = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers)

    assert res.status_code == 200, res.text
    invited = [row for row in res.json()["data"] if row["account"] == "INVITED"]
    assert len(invited) == 1
    assert invited[0]["name"] == "new-officer@example.com"
    assert invited[0]["group"] == "임원"
    assert invited[0]["subtitle"] == "운영진"


async def test_계정_없는_명단_전용_동아리원도_NONE으로_보인다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)

    sessionmaker = db_session.get_sessionmaker()
    async with sessionmaker() as session:
        session.add(
            Member(
                club_id=club_id,
                account_id=None,
                name="명단만 있는 회원",
                role=MemberRole.MEMBER,
                status=MemberStatus.ACTIVE,
                student_no="21",
            )
        )
        await session.commit()

    res = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers)

    assert res.status_code == 200, res.text
    roster_only = next(
        row for row in res.json()["data"] if row["name"] == "명단만 있는 회원"
    )
    assert roster_only["account"] == "NONE"
    assert roster_only["group"] == "동아리원"
    assert roster_only["subtitle"] == "21학번"
    assert roster_only["accountAt"] is None


async def test_동아리원이_아니면_명단을_볼_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    outsider_headers = _login(client, "mem-outsider")

    res = client.get(f"/api/v1/clubs/{club_id}/members", headers=outsider_headers)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"
