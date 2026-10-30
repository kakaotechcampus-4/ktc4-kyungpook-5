"""인증(DB 세션)·동아리·멤버십 API의 응답 계약과 실제 동작 테스트 (#131).

service-flow.curl.sh 01~10번이 실제 DB로 끝까지 도는지 확인한다.
"""

import uuid
import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import session as db_session
from app.core.exceptions import ValidationFailed
from app.models.auth import Account
from app.services import club_service

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


async def test_초대_수락하면_해당_역할로_가입된다(
    client: TestClient, app_db: None, capsys: pytest.CaptureFixture[str]
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

    # 더미 발송은 print()로만 나간다 — capsys로 콘솔 출력에서 토큰을 꺼낸다.
    printed = capsys.readouterr().out
    invite_token = printed.strip().rsplit(": ", 1)[-1]

    _signup(client, manager_email, name="매니저")
    manager_token, _ = _login(client, manager_email)

    accept_res = client.post(
        "/api/v1/invitations/accept",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"token": invite_token},
    )
    assert accept_res.status_code == 200, accept_res.text
    assert accept_res.json()["data"] == {"clubId": club_id, "role": "MANAGER"}

    me_res = client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {manager_token}"}
    )
    assert me_res.json()["data"]["clubs"] == [
        {"id": club_id, "name": "초대 테스트 동아리", "role": "MANAGER"}
    ]


async def test_초대_동시_수락은_한_번만_성공한다(client: TestClient, app_db: None) -> None:
    owner_email = _unique_email("invite-lock-owner")
    _signup(client, owner_email)
    owner_token, _ = _login(client, owner_email)
    club_id = client.post("/api/v1/clubs", headers={"Authorization": f"Bearer {owner_token}"},
                          json={"name": "동시 초대"}).json()["data"]["id"]
    invite = client.post(f"/api/v1/clubs/{club_id}/invitations",
                         headers={"Authorization": f"Bearer {owner_token}"},
                         json={"role": "MANAGER"}).json()["data"]
    emails = [_unique_email("invite-lock-a"), _unique_email("invite-lock-b")]
    accounts = []
    for email in emails:
        _signup(client, email)
        accounts.append(email)
    factory = db_session.get_sessionmaker()
    async def accept(email: str):
        async with factory() as session:
            account = await session.scalar(select(Account).where(Account.email == email))
            return await club_service.accept_invitation(session, token=invite["token"], account=account)
    results = await asyncio.gather(*(accept(email) for email in accounts), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ValidationFailed) for result in results) == 1


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
