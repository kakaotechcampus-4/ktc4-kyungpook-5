"""인증(DB 세션)·동아리·멤버십 API의 응답 계약과 실제 동작 테스트 (#131).

service-flow.curl.sh 01~10번이 실제 DB로 끝까지 도는지 확인한다.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import InvitationStatus
from app.db import session as db_session
from app.main import app
from app.models.clubs import Invitation

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


def _signup(client: TestClient, email: str, name: str = "테스트") -> str:
    """가입만 하고 accountId를 돌려준다. 이메일 인증은 하지 않는다 —
    로그인 자체는 email_verified 여부와 무관하게 허용한다(#131 설계)."""
    signup_res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "name": name},
    )
    assert signup_res.status_code == 201, signup_res.text
    return signup_res.json()["data"]["id"]


def _login(client: TestClient, email: str) -> tuple[str, str]:
    res = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    return data["accessToken"], data["refreshToken"]


async def test_가입_후_me는_빈_동아리_목록이다(client: TestClient, app_db: None) -> None:
    email = _unique_email("owner")
    _signup(client, email)
    access_token, _ = _login(client, email)

    res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access_token}"})

    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["clubs"] == []
    assert body["data"]["emailVerified"] is False


async def test_가입_토큰으로_이메일_인증하면_me에_반영된다(
    client: TestClient, app_db: None, capsys: pytest.CaptureFixture[str]
) -> None:
    email = _unique_email("verify")
    _signup(client, email)
    token = capsys.readouterr().out.strip().rsplit(": ", 1)[-1]

    verify_res = client.post("/api/v1/auth/email/verify", json={"token": token})
    assert verify_res.status_code == 200
    assert verify_res.json()["data"]["emailVerified"] is True

    access_token, _ = _login(client, email)
    me_res = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_res.json()["data"]["emailVerified"] is True


async def test_같은_이메일로_두번_가입하면_422(client: TestClient, app_db: None) -> None:
    email = _unique_email("dup")
    _signup(client, email)

    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "name": "다시"},
    )

    assert res.status_code == 422
    body = res.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert "detail" not in body


async def test_틀린_비밀번호면_401(client: TestClient, app_db: None) -> None:
    email = _unique_email("wrongpw")
    _signup(client, email)

    res = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "완전히-틀림"}
    )

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


async def test_인증_없이_me_호출하면_401(client: TestClient, app_db: None) -> None:
    res = client.get("/api/v1/me")

    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


async def test_동아리_생성하면_OWNER로_me에_나온다(client: TestClient, app_db: None) -> None:
    email = _unique_email("creator")
    _signup(client, email)
    access_token, _ = _login(client, email)
    headers = {"Authorization": f"Bearer {access_token}"}

    create_res = client.post(
        "/api/v1/clubs",
        headers=headers,
        json={"name": "테스트 동아리", "category": "HOBBY", "description": "e2e"},
    )
    assert create_res.status_code == 201, create_res.text
    club_id = create_res.json()["data"]["id"]

    me_res = client.get("/api/v1/me", headers=headers)
    clubs = me_res.json()["data"]["clubs"]
    assert clubs == [{"id": club_id, "name": "테스트 동아리", "role": "OWNER"}]


async def test_refresh_회전후_예전_refresh_토큰은_401(
    client: TestClient, app_db: None
) -> None:
    email = _unique_email("rotate")
    _signup(client, email)
    _, refresh_token = _login(client, email)

    first = client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert first.status_code == 200

    reuse = client.post("/api/v1/auth/refresh", json={"refreshToken": refresh_token})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "UNAUTHORIZED"


async def test_logout_후_refresh는_401(client: TestClient, app_db: None) -> None:
    email = _unique_email("logout")
    _signup(client, email)
    access_token, refresh_token = _login(client, email)
    headers = {"Authorization": f"Bearer {access_token}"}

    logout_res = client.post(
        "/api/v1/auth/logout", headers=headers, json={"refreshToken": refresh_token}
    )
    assert logout_res.status_code == 204

    refresh_res = client.post(
        "/api/v1/auth/refresh", json={"refreshToken": refresh_token}
    )
    assert refresh_res.status_code == 401


async def test_한_초대를_여러_계정이_동시에_수락하고_중복_가입은_막는다(
    client: TestClient, app_db: None
) -> None:
    owner_email = _unique_email("inv-owner")
    _signup(client, owner_email)
    owner_token, _ = _login(client, owner_email)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    club_res = client.post(
        "/api/v1/clubs", headers=owner_headers, json={"name": "초대 테스트 동아리"}
    )
    club_id = club_res.json()["data"]["id"]

    manager_email = _unique_email("inv-manager")
    invite_res = client.post(
        f"/api/v1/clubs/{club_id}/invitations",
        headers=owner_headers,
        json={"email": manager_email, "role": "MANAGER"},
    )
    assert invite_res.status_code == 201, invite_res.text

    invite_token = invite_res.json()["data"]["token"]
    assert invite_res.json()["data"]["expiresAt"]

    _signup(client, manager_email, name="매니저")
    manager_token, _ = _login(client, manager_email)

    second_email = _unique_email("inv-second")
    _signup(client, second_email)
    second_token, _ = _login(client, second_email)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        def accept(token: str):
            return ac.post(
                "/api/v1/invitations/accept",
                headers={"Authorization": f"Bearer {token}"},
                json={"token": invite_token},
            )

        first, second, duplicate = await asyncio.gather(
            accept(manager_token), accept(second_token), accept(manager_token)
        )

    assert second.status_code == 200, second.text
    assert sorted((first.status_code, duplicate.status_code)) == [200, 422]
    for accepted in (second, first if first.status_code == 200 else duplicate):
        assert accepted.json()["data"] == {"clubId": club_id, "role": "MANAGER"}

    me_res = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert me_res.json()["data"]["clubs"] == [
        {"id": club_id, "name": "초대 테스트 동아리", "role": "MANAGER"}
    ]

    roster = client.get(f"/api/v1/clubs/{club_id}/members", headers=owner_headers)
    assert roster.status_code == 200, roster.text
    rows = roster.json()["data"]
    assert len(rows) == 3
    assert {row["account"] for row in rows} == {"JOINED"}

    sessionmaker = db_session.get_sessionmaker()
    async with sessionmaker() as session:
        invitation = await session.scalar(select(Invitation).where(Invitation.club_id == club_id))
        assert invitation.status == InvitationStatus.PENDING
        assert invitation.accepted_at is not None
        assert invitation.accepted_by is not None


@pytest.mark.parametrize("already_consumed", [False, True])
async def test_만료됐거나_이전_버전에서_사용된_초대는_수락할_수_없다(
    client: TestClient, app_db: None, already_consumed: bool
) -> None:
    owner_email = _unique_email("inv-closed-owner")
    _signup(client, owner_email)
    owner_token, _ = _login(client, owner_email)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    club_res = client.post("/api/v1/clubs", headers=owner_headers, json={"name": "만료 테스트"})
    club_id = club_res.json()["data"]["id"]

    member_email = _unique_email("inv-closed-member")
    _signup(client, member_email)
    member_token, _ = _login(client, member_email)
    invite_res = client.post(
        f"/api/v1/clubs/{club_id}/invitations",
        headers=owner_headers,
        json={"email": member_email, "role": "MANAGER"},
    )
    assert invite_res.status_code == 201, invite_res.text
    invite = invite_res.json()["data"]
    sessionmaker = db_session.get_sessionmaker()
    async with sessionmaker() as session:
        invitation = await session.get(Invitation, invite["id"])
        if already_consumed:
            invitation.status = InvitationStatus.ACCEPTED
        else:
            invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    res = client.post(
        "/api/v1/invitations/accept",
        headers={"Authorization": f"Bearer {member_token}"},
        json={"token": invite["token"]},
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["fields"]["token"] == (
        "이미 처리된 초대입니다." if already_consumed else "초대가 만료되었습니다."
    )


async def test_권한_없는_멤버는_초대를_못_만든다(client: TestClient, app_db: None) -> None:
    owner_email = _unique_email("perm-owner")
    _signup(client, owner_email)
    owner_token, _ = _login(client, owner_email)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    club_res = client.post(
        "/api/v1/clubs", headers=owner_headers, json={"name": "권한 테스트"}
    )
    club_id = club_res.json()["data"]["id"]

    outsider_email = _unique_email("outsider")
    _signup(client, outsider_email)
    outsider_token, _ = _login(client, outsider_email)

    res = client.post(
        f"/api/v1/clubs/{club_id}/invitations",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={"email": "someone@example.com", "role": "MANAGER"},
    )

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"
