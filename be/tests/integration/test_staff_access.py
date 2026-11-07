"""기존 MEMBER 데이터는 보존하면서 회장·임원에게만 업무 접근을 허용한다."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.core.enums import InvitationStatus, MemberRole
from app.core.security import hash_token
from app.db import session as db_session
from app.models.clubs import Invitation, Member

pytestmark = [pytest.mark.db, pytest.mark.anyio]
PASSWORD = "StaffTest-2027!"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _account(client: TestClient, tag: str) -> dict:
    email = f"staff-{tag}-{uuid.uuid4().hex[:12]}@example.com"
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "name": tag},
    )
    assert signup.status_code == 201, signup.text
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["accessToken"]
    return {
        "id": signup.json()["data"]["id"],
        "email": email,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _club(client: TestClient, account: dict) -> str:
    result = client.post(
        "/api/v1/clubs", headers=account["headers"], json={"name": "운영진 접근 검사"}
    )
    assert result.status_code == 201, result.text
    return result.json()["data"]["id"]


async def _legacy_member(account: dict, club_id: str, role: MemberRole) -> str:
    # 이전 버전 DB의 MEMBER를 재현한다. 신규 초대 API로 만들 수 없어야 한다.
    async with db_session.get_sessionmaker()() as session:
        member = Member(
            club_id=club_id, account_id=account["id"], name=role.value, role=role
        )
        session.add(member)
        await session.commit()
        return member.id


def _meeting(client: TestClient, account: dict, club_id: str) -> str:
    result = client.post(
        f"/api/v1/clubs/{club_id}/meetings",
        headers=account["headers"],
        json={"title": "운영 회의", "recordingConsentConfirmed": True},
    )
    assert result.status_code == 201, result.text
    return result.json()["data"]["id"]


async def test_legacy_member_club_is_hidden_but_identity_and_new_owner_onboarding_remain(
    client: TestClient, app_db: None
) -> None:
    owner, ordinary = _account(client, "owner"), _account(client, "ordinary")
    old_club = _club(client, owner)
    legacy_id = await _legacy_member(ordinary, old_club, MemberRole.MEMBER)

    me = client.get("/api/v1/me", headers=ordinary["headers"])
    assert me.status_code == 200, me.text
    assert me.json()["data"]["id"] == ordinary["id"]
    assert me.json()["data"]["clubs"] == []

    # MEMBER인 계정을 전역 정지하지 않는다. 새 동아리의 회장으로 시작할 수 있다.
    new_club = _club(client, ordinary)
    clubs = client.get("/api/v1/me", headers=ordinary["headers"]).json()["data"]["clubs"]
    assert clubs == [{"id": new_club, "name": "운영진 접근 검사", "role": "OWNER"}]
    async with db_session.get_sessionmaker()() as session:
        assert (await session.get(Member, legacy_id)).role == MemberRole.MEMBER


async def test_legacy_member_cannot_read_records_expenses_meeting_transcripts_or_join_ws(
    client: TestClient, app_db: None
) -> None:
    owner, ordinary = _account(client, "owner"), _account(client, "ordinary")
    club_id = _club(client, owner)
    await _legacy_member(ordinary, club_id, MemberRole.MEMBER)
    meeting_id = _meeting(client, owner, club_id)

    for path in (
        f"/api/v1/records?clubId={club_id}",
        f"/api/v1/clubs/{club_id}/expenses",
        f"/api/v1/meetings/{meeting_id}",
        f"/api/v1/meetings/{meeting_id}/transcripts",
    ):
        result = client.get(path, headers=ordinary["headers"])
        assert result.status_code == 403, (path, result.text)
        assert result.json()["error"]["code"] == "FORBIDDEN"
    created = client.post(
        f"/api/v1/clubs/{club_id}/meetings",
        headers=ordinary["headers"],
        json={"title": "허용되지 않는 회의", "recordingConsentConfirmed": True},
    )
    assert created.status_code == 403, created.text
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            f"/api/v1/meetings/{meeting_id}/stream?token={ordinary['token']}"
        ):
            pass
    assert denied.value.code == 4403


@pytest.mark.parametrize("role", [MemberRole.OWNER, MemberRole.MANAGER])
async def test_chair_and_committee_keep_business_http_and_ws_access(
    client: TestClient, app_db: None, role: MemberRole
) -> None:
    owner = _account(client, "owner")
    club_id = _club(client, owner)
    actor = owner
    if role == MemberRole.MANAGER:
        actor = _account(client, "committee")
        await _legacy_member(actor, club_id, role)
    meeting_id = _meeting(client, actor, club_id)

    me = client.get("/api/v1/me", headers=actor["headers"])
    assert me.json()["data"]["clubs"] == [
        {"id": club_id, "name": "운영진 접근 검사", "role": role.value}
    ]
    for path in (
        f"/api/v1/records?clubId={club_id}",
        f"/api/v1/clubs/{club_id}/expenses",
        f"/api/v1/meetings/{meeting_id}",
        f"/api/v1/meetings/{meeting_id}/transcripts",
    ):
        result = client.get(path, headers=actor["headers"])
        assert result.status_code == 200, (path, result.text)
    with client.websocket_connect(
        f"/api/v1/meetings/{meeting_id}/stream?token={actor['token']}"
    ):
        pass


@pytest.mark.parametrize("role", ["MEMBER", "ADMIN"])
async def test_new_invitations_only_accept_service_staff_roles(
    client: TestClient, app_db: None, role: str
) -> None:
    owner = _account(client, "owner")
    club_id = _club(client, owner)
    result = client.post(
        f"/api/v1/clubs/{club_id}/invitations",
        headers=owner["headers"],
        json={"email": "not-staff@example.com", "role": role},
    )
    assert result.status_code == 422, result.text
    assert result.json()["error"]["code"] == "VALIDATION_FAILED"
    async with db_session.get_sessionmaker()() as session:
        assert await session.scalar(
            select(Invitation.id).where(Invitation.club_id == club_id)
        ) is None


async def test_legacy_pending_member_invitation_cannot_create_membership(
    client: TestClient, app_db: None
) -> None:
    owner, invitee = _account(client, "owner"), _account(client, "invitee")
    club_id = _club(client, owner)
    token = uuid.uuid4().hex
    async with db_session.get_sessionmaker()() as session:
        chair = await session.scalar(select(Member).where(Member.club_id == club_id))
        invitation = Invitation(
            club_id=club_id,
            email=invitee["email"],
            role=MemberRole.MEMBER,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            invited_by=chair.id,
        )
        session.add(invitation)
        await session.commit()
        invitation_id = invitation.id

    result = client.post(
        "/api/v1/invitations/accept",
        headers=invitee["headers"],
        json={"token": token},
    )
    assert result.status_code == 422, result.text
    assert result.json()["error"]["code"] == "VALIDATION_FAILED"
    async with db_session.get_sessionmaker()() as session:
        assert await session.scalar(
            select(Member.id).where(
                Member.club_id == club_id, Member.account_id == invitee["id"]
            )
        ) is None
        invitation = await session.get(Invitation, invitation_id)
        assert invitation.status == InvitationStatus.PENDING
        assert invitation.accepted_by is None
