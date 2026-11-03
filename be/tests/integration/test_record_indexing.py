"""공개 AI 경계만 대체하고 PostgreSQL 색인·검색 scope를 실제 검증한다."""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import ai
from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.db import session as db_session
from app.models.record_chunks import RecordChunk
from app.models.records import Record
from app.services.record_search_port import PostgresRecordSearch

pytestmark = [pytest.mark.db, pytest.mark.anyio]
VECTOR = (1.0,) + (0.0,) * (ai.EMBEDDING_DIMENSIONS - 1)
RULES_CSV = "조항,내용\n제7조,행사를 취소할 때는 행사 시작 7일 전까지 공지한다.\n".encode()


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None, tmp_path,
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    yield
    await db_session.get_engine().dispose()


def _owner(client: TestClient) -> dict:
    email = f"index-{uuid.uuid4().hex}@example.com"
    result = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "PmTest-2027!", "name": "색인 테스트",
    })
    assert result.status_code == 201, result.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "PmTest-2027!"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}


def _club(client: TestClient, headers: dict) -> str:
    result = client.post("/api/v1/clubs", headers=headers, json={"name": "검색 범위 테스트"})
    assert result.status_code == 201, result.text
    return result.json()["data"]["id"]


def _upload(client: TestClient, headers: dict, club_id: str, category="RULES") -> dict:
    result = client.post("/api/v1/records", headers=headers,
        data={"clubId": club_id, "category": category},
        files={"file": ("rules.csv", RULES_CSV, "text/csv")})
    assert result.status_code == 201, result.text
    return result.json()["data"]


async def test_upload_persists_public_ai_chunks_and_new_session_search_respects_scope(client, app_db, monkeypatch) -> None:
    requests = []

    async def fake_index(request):
        requests.append(request)
        return ai.IndexRecordResult(chunks=tuple(
            ai.IndexedChunk(text=block.text, location=block.location,
                            block_indexes=(index,), embedding=VECTOR)
            for index, block in enumerate(request.blocks)
        ))

    monkeypatch.setattr(ai, "index_record", fake_index)
    headers = _owner(client)
    club_id, other_club_id = _club(client, headers), _club(client, headers)
    own = _upload(client, headers, club_id)
    outside = _upload(client, headers, other_club_id)
    own_other_category = _upload(client, headers, club_id, "ETC")
    assert own["parseStatus"] == "INDEXED" and own["indexError"] is None
    assert requests[0].record_id == own["id"] and requests[0].blocks
    assert requests[0].file_type == RecordFileType.CSV
    factory = db_session.get_sessionmaker()
    # 업로드 요청과 다른 세션으로 읽어 in-memory 검색 대체를 막는다.
    async with factory() as session:
        record = await session.get(Record, own["id"])
        chunks = list(await session.scalars(select(RecordChunk).where(RecordChunk.record_id == own["id"])))
        assert record.parse_status == RecordParseStatus.INDEXED
        assert len(chunks) == len(requests[0].blocks)
        assert chunks[0].text == requests[0].blocks[0].text
        assert chunks[0].location == requests[0].blocks[0].location.model_dump(mode="json")
        assert len(chunks[0].embedding) == ai.EMBEDDING_DIMENSIONS
        assert chunks[0].block_indexes == [0]
        # 오래된 청크가 남아 있어도 자료 상태가 INDEXED가 아니면 조회하지 않는다.
        unready = Record(club_id=club_id, file_name="unready.csv", file_type=RecordFileType.CSV,
                         category=RecordCategory.RULES, storage_key="fixture/unready.csv", size=1,
                         parse_status=RecordParseStatus.COMPLETED, parse_result={"blocks": []})
        session.add(unready)
        await session.flush()
        session.add(RecordChunk(record_id=unready.id, chunk_index=0, text="보이면 안 되는 미준비 자료",
                                location={"label": "1행"}, block_indexes=[0], embedding=list(VECTOR)))
        await session.commit()
        unready_id = unready.id

    port = PostgresRecordSearch(club_id, session_factory=factory)
    hits = await port.search_chunks(ai.ChunkSearchQuery(club_id=club_id, embedding=VECTOR, limit=20))
    ids = {hit.source.record_id for hit in hits}
    assert own["id"] in ids and own_other_category["id"] in ids
    assert outside["id"] not in ids and unready_id not in ids
    assert all(hit.source.location.label for hit in hits)
    filtered = await port.search_chunks(ai.ChunkSearchQuery(
        club_id=club_id, embedding=VECTOR, limit=20, category=RecordCategory.RULES))
    assert {hit.source.record_id for hit in filtered} == {own["id"]}
    with pytest.raises(ValueError, match="범위"):
        await port.search_chunks(ai.ChunkSearchQuery(club_id=other_club_id, embedding=VECTOR, limit=1))
    # 이미 INDEXED인 재시도는 청크/모델 호출을 추가하지 않는다.
    previous_calls = len(requests)
    retried = client.post(f"/api/v1/records/{own['id']}/index", headers=headers)
    assert retried.status_code == 200 and len(requests) == previous_calls


async def test_index_configuration_failure_keeps_parsed_record_and_safe_error(client, app_db, monkeypatch) -> None:
    async def unconfigured(request):
        raise ai.AIConfigError("raw-secret-should-never-be-returned")

    monkeypatch.setattr(ai, "index_record", unconfigured)
    headers = _owner(client)
    club_id = _club(client, headers)
    saved = _upload(client, headers, club_id)
    assert saved["parseStatus"] == "COMPLETED"
    assert saved["indexError"]["code"] == "AIConfigError"
    assert "raw-secret" not in str(saved)
    detail = client.get(f"/api/v1/records/{saved['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["parseResult"]["blocks"]
    async with db_session.get_sessionmaker()() as session:
        record = await session.get(Record, saved["id"])
        assert record.parse_status == RecordParseStatus.COMPLETED
        assert record.parse_result["blocks"]
        assert not list(await session.scalars(select(RecordChunk).where(RecordChunk.record_id == saved["id"])))
