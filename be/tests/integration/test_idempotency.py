"""Idempotency-Key 처리 테스트 (#187, PR #209 리뷰).

오래 남은 PROCESSING 키를 두 요청이 동시에 이어받으려 할 때 한 요청만 처리 권한을
얻는지 본다. 두 DB 세션이 같은 오래된 행을 읽은 뒤 갱신하는 순서를 직접 만든다.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core import idempotency
from app.core.exceptions import IdempotencyInProgress
from app.db import session as db_session
from app.models.common import IdempotencyKey

pytestmark = [pytest.mark.db, pytest.mark.anyio]

PASSWORD = "PmTest-2027!"
ENDPOINT = "POST /events/{event_id}/plan/chat"
BODY = b'{"message": "MT"}'


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _member(client: TestClient) -> tuple[str, str]:
    """(club_id, member_id). 멱등키 행은 동아리원을 외래키로 가리킨다."""
    email = f"idem-{uuid.uuid4().hex[:12]}@example.com"
    client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "idem"})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}
    club_id = client.post("/api/v1/clubs", headers=headers, json={"name": "idem"}).json()[
        "data"
    ]["id"]
    members = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers).json()["data"]
    return club_id, members[0]["id"]


async def _resolve(session, club_id: str, member_id: str, key: str):
    return await idempotency.resolve(
        session, key=key, club_id=club_id, member_id=member_id,
        endpoint=ENDPOINT, request_body=BODY,
    )


async def test_오래된_처리_중_키는_동시에_와도_한_요청만_이어받는다(
    client: TestClient, app_db: None
) -> None:
    club_id, member_id = _member(client)
    sessionmaker = db_session.get_sessionmaker()
    async with sessionmaker() as session:
        session.add(
            IdempotencyKey(
                club_id=club_id, member_id=member_id, endpoint=ENDPOINT,
                idempotency_key="stale", status="PROCESSING",
                request_body_hash=idempotency.hashlib.sha256(BODY).hexdigest(),
                modified_at=datetime.now(UTC) - timedelta(minutes=10),
            )
        )
        await session.commit()

    async with sessionmaker() as first, sessionmaker() as second:
        # 첫 요청이 이어받고 아직 커밋하지 않은 사이에 두 번째 요청이 같은 오래된 행을 읽는다.
        taken = await _resolve(first, club_id, member_id, "stale")
        racing = asyncio.create_task(_resolve(second, club_id, member_id, "stale"))
        await asyncio.sleep(0.3)
        # 두 번째 요청은 오래된 행을 읽고 갱신하려다 첫 요청의 행 잠금에서 기다리는 중이다.
        assert not racing.done()
        await first.commit()

        with pytest.raises(IdempotencyInProgress):
            await racing

    assert taken is not None and taken.is_replay is False
