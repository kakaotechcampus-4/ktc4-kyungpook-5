"""회의 세션·전사 API의 응답 계약과 실제 동작 테스트 (#135).

meeting.curl.sh의 M02, M05~M09(실제 음성 대신 test-support 경로)가 실제 DB로
끝까지 도는지 확인한다. 판단은 더미(services/meeting_judge_stub.py)다.
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


def _unique_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:12]}@example.com"


def _owner_with_club(client: TestClient) -> tuple[str, str]:
    email = _unique_email("mtg-owner")
    signup = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": PASSWORD, "name": "회의 테스트"},
    )
    assert signup.status_code == 201, signup.text
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    access_token = login.json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {access_token}"}
    club = client.post(
        "/api/v1/clubs", headers=headers, json={"name": "회의 테스트 동아리"}
    )
    assert club.status_code == 201, club.text
    return access_token, club.json()["data"]["id"]


def _start_meeting(client: TestClient, headers: dict, club_id: str) -> str:
    res = client.post(
        f"/api/v1/clubs/{club_id}/meetings",
        headers=headers,
        json={
            "title": "Test Meeting",
            "language": "ko-KR",
            "recordingConsentConfirmed": True,
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["status"] == "RECORDING"
    return res.json()["data"]["id"]


async def test_회의를_시작하면_RECORDING_상태다(client: TestClient, app_db: None) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    meeting_id = _start_meeting(client, headers, club_id)

    res = client.get(f"/api/v1/meetings/{meeting_id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "RECORDING"


async def test_물음표_없는_발화는_NONE으로_판단된다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)

    res = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": 1, "startMs": 0, "endMs": 3000, "final": True, "text": "회의를 시작하겠습니다"},
    )

    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["route"] == "NONE"
    assert body["kind"] == "NO_LOOKUP"
    assert body["question"] is None


async def test_물음표_있는_발화는_RAG로_판단된다(client: TestClient, app_db: None) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)

    res = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={
            "seq": 1,
            "startMs": 0,
            "endMs": 3000,
            "final": True,
            "text": "작년 MT 숙소비 얼마였지?",
        },
    )

    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["route"] == "RAG"
    assert body["kind"] == "NOT_FOUND"
    assert body["question"] == "작년 MT 숙소비 얼마였지?"
    assert body["trace"]["toolCalls"][0]["tool"] == "records.search"


async def test_같은_seq_정정은_expectedVersion_없으면_409(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)
    client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": 1, "startMs": 0, "endMs": 3000, "final": True, "text": "hello"},
    )

    retry = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": 1, "startMs": 0, "endMs": 3000, "final": True, "text": "hello again"},
    )

    assert retry.status_code == 409
    assert retry.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_expectedVersion과_함께_정정하면_버전이_오르고_다시_판단한다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)
    first = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": 1, "startMs": 0, "endMs": 3000, "final": True, "text": "hello"},
    )
    assert first.json()["data"]["version"] == 1

    corrected = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={
            "seq": 1,
            "startMs": 0,
            "endMs": 3000,
            "final": True,
            "text": "작년 MT 숙소비 얼마였지?",
            "expectedVersion": 1,
        },
    )

    assert corrected.status_code == 201, corrected.text
    body = corrected.json()["data"]
    assert body["version"] == 2
    assert body["route"] == "RAG"


async def test_회의를_종료하면_COMPLETED가_된다(client: TestClient, app_db: None) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)

    res = client.post(f"/api/v1/meetings/{meeting_id}/finish", headers=headers)

    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "COMPLETED"


async def test_다른_동아리_사람은_회의를_못_본다(client: TestClient, app_db: None) -> None:
    owner_token, club_id = _owner_with_club(client)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    meeting_id = _start_meeting(client, owner_headers, club_id)

    outsider_email = _unique_email("mtg-outsider")
    client.post(
        "/api/v1/auth/signup",
        json={"email": outsider_email, "password": PASSWORD, "name": "외부인"},
    )
    outsider_login = client.post(
        "/api/v1/auth/login", json={"email": outsider_email, "password": PASSWORD}
    )
    outsider_headers = {
        "Authorization": f"Bearer {outsider_login.json()['data']['accessToken']}"
    }

    res = client.get(f"/api/v1/meetings/{meeting_id}", headers=outsider_headers)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


async def test_WebSocket으로_판단_결과가_실시간으로_전달된다(
    client: TestClient, app_db: None
) -> None:
    access_token, club_id = _owner_with_club(client)
    headers = {"Authorization": f"Bearer {access_token}"}
    meeting_id = _start_meeting(client, headers, club_id)

    with client.websocket_connect(
        f"/api/v1/meetings/{meeting_id}/stream?token={access_token}"
    ) as ws:
        res = client.post(
            f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
            headers=headers,
            json={
                "seq": 1,
                "startMs": 0,
                "endMs": 3000,
                "final": True,
                "text": "작년 MT 숙소비 얼마였지?",
            },
        )
        assert res.status_code == 201, res.text

        stage_msg = ws.receive_json()
        assert stage_msg["type"] == "stage"
        assert stage_msg["stage"] == "JUDGING"

        searching_msg = ws.receive_json()
        assert searching_msg == {
            "type": "stage",
            "segmentId": stage_msg["segmentId"],
            "seq": 1,
            "stage": "SEARCHING",
        }

        judgment_msg = ws.receive_json()
        assert judgment_msg["type"] == "judgment"
        assert judgment_msg["route"] == "RAG"
        assert judgment_msg["question"] == "작년 MT 숙소비 얼마였지?"
