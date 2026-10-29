"""기록 색인(RecordChunk 저장)과 DbRecordSearchPort 검색 테스트 (#141).

app.ai.index_record는 monkeypatch로 고정된 임베딩을 돌려주게 해서, 실제 임베딩
호출(AI_API_KEY 필요) 없이 pgvector 저장·코사인 유사도 검색만 검증한다.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

import app.ai as ai
from app.ai import ChunkSearchQuery
from app.db import session as db_session
from app.services.record_search_port import DbRecordSearchPort

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
    headers = _login(client, "chunk-owner")
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "청크 테스트 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


def _vector(seed: float) -> tuple[float, ...]:
    # 코사인 유사도 비교용 저차원 패턴을 1536차원으로 반복한다.
    base = (seed, 1 - seed, 0.0)
    return tuple((base * ((ai.EMBEDDING_DIMENSIONS // 3) + 1))[: ai.EMBEDDING_DIMENSIONS])


def _upload_with_fixed_embedding(
    client: TestClient, headers: dict, club_id: str, *, category: str,
    file_name: str, embedding: tuple[float, ...], monkeypatch: pytest.MonkeyPatch,
) -> str:
    async def fake_index_record(request):
        return ai.IndexRecordResult(
            chunks=(
                ai.IndexedChunk(
                    text=request.blocks[0].text, location=request.blocks[0].location,
                    block_indexes=(0,), embedding=embedding,
                ),
            )
        )

    monkeypatch.setattr("app.ai.index_record", fake_index_record)
    res = client.post(
        "/api/v1/records", headers=headers,
        data={"clubId": club_id, "category": category},
        files={"file": (file_name, b"a,b\n1,2\n", "text/csv")},
    )
    assert res.status_code == 201, res.text
    record_id = res.json()["data"]["id"]
    detail = client.get(f"/api/v1/records/{record_id}", headers=headers).json()["data"]
    assert detail["parseStatus"] == "INDEXED"
    return record_id


async def test_올린_기록과_똑같은_임베딩으로_검색하면_점수가_1에_가깝다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    embedding = _vector(0.9)
    record_id = _upload_with_fixed_embedding(
        client, headers, club_id, category="RULES", file_name="rules.csv",
        embedding=embedding, monkeypatch=monkeypatch,
    )

    async with db_session.get_sessionmaker()() as session:
        port = DbRecordSearchPort(session)
        results = await port.search_chunks(
            ChunkSearchQuery(club_id=club_id, embedding=embedding, limit=5)
        )

    assert len(results) == 1
    assert results[0].source.record_id == record_id
    assert results[0].source.file_name == "rules.csv"
    assert results[0].category == "RULES"
    assert results[0].score == pytest.approx(1.0, abs=1e-4)


async def test_category로_거른다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    embedding = _vector(0.5)
    _upload_with_fixed_embedding(
        client, headers, club_id, category="RULES", file_name="rules.csv",
        embedding=embedding, monkeypatch=monkeypatch,
    )
    _upload_with_fixed_embedding(
        client, headers, club_id, category="LEDGER", file_name="ledger.csv",
        embedding=embedding, monkeypatch=monkeypatch,
    )

    async with db_session.get_sessionmaker()() as session:
        port = DbRecordSearchPort(session)
        results = await port.search_chunks(
            ChunkSearchQuery(club_id=club_id, embedding=embedding, limit=5, category="LEDGER")
        )

    assert len(results) == 1
    assert results[0].source.file_name == "ledger.csv"


async def test_다른_동아리의_청크는_검색되지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    embedding = _vector(0.7)
    _upload_with_fixed_embedding(
        client, headers, club_id, category="ETC", file_name="mine.csv",
        embedding=embedding, monkeypatch=monkeypatch,
    )
    other_headers, other_club_id = _owner_with_club(client)
    _upload_with_fixed_embedding(
        client, other_headers, other_club_id, category="ETC", file_name="theirs.csv",
        embedding=embedding, monkeypatch=monkeypatch,
    )

    async with db_session.get_sessionmaker()() as session:
        port = DbRecordSearchPort(session)
        results = await port.search_chunks(
            ChunkSearchQuery(club_id=club_id, embedding=embedding, limit=5)
        )

    assert len(results) == 1
    assert results[0].source.file_name == "mine.csv"


async def test_유사도_낮은_청크는_뒤로_밀린다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    query_embedding = _vector(1.0)
    close_embedding = _vector(0.95)
    far_embedding = _vector(0.1)
    _upload_with_fixed_embedding(
        client, headers, club_id, category="ETC", file_name="far.csv",
        embedding=far_embedding, monkeypatch=monkeypatch,
    )
    _upload_with_fixed_embedding(
        client, headers, club_id, category="ETC", file_name="close.csv",
        embedding=close_embedding, monkeypatch=monkeypatch,
    )

    async with db_session.get_sessionmaker()() as session:
        port = DbRecordSearchPort(session)
        results = await port.search_chunks(
            ChunkSearchQuery(club_id=club_id, embedding=query_embedding, limit=5)
        )

    assert [r.source.file_name for r in results] == ["close.csv", "far.csv"]
    assert results[0].score > results[1].score
