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


async def test_자료검색_본문과_파일명_페이지_권한(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    from app.core.config import get_settings

    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    async def no_index(_request):
        raise ai.AIConfigError('fixture')
    monkeypatch.setattr(ai, 'index_record', no_index)
    headers, club_id = _owner_with_club(client)
    for name, content in [('budget.csv', '항목,금액\n간식,5000\n'), ('간식.csv', '이름,값\n물,10\n')]:
        response = client.post('/api/v1/records', headers=headers, data={'clubId': club_id},
                               files={'file': (name, content.encode(), 'text/csv')})
        assert response.status_code == 201
    other, other_club = _owner_with_club(client)
    _upload(client, other, other_club, 'ETC', '간식-secret.csv')
    params = {'clubId': club_id, 'query': '간식', 'size': 1}
    first = client.get('/api/v1/records/search', headers=headers, params=params)
    second = client.get('/api/v1/records/search', headers=headers, params={**params, 'page': 2})
    assert first.status_code == second.status_code == 200
    assert first.json()['meta']['totalCount'] == 2
    assert first.json()['data']['semanticStatus'] == 'NO_INDEXED_RECORDS'
    assert first.json()['data']['unindexedCount'] == 2
    a, b = first.json()['data']['items'][0], second.json()['data']['items'][0]
    assert a['fileName'] == '간식.csv' and a['matchTypes'] == ['FILENAME']
    assert b['fileName'] == 'budget.csv' and b['matchTypes'] == ['CONTENT']
    assert '간식' in b['excerpts'][0]['text'] and b['excerpts'][0]['location']['label']
    assert client.get('/api/v1/records/search', headers=headers, params={'clubId': other_club, 'query':'간식'}).status_code == 403
    assert client.get('/api/v1/records/search', headers=headers, params={'clubId': club_id, 'query':'  '}).status_code == 422
    assert client.get('/api/v1/records/search', headers=headers, params={'clubId': club_id, 'query':'%'}).json()['meta']['totalCount'] == 0


async def test_자료검색_공개AI와_pgvector_및_부분실패(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    from app.ai.features.retrieval import nodes
    from app.core.config import get_settings
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    vector = (1.0,) + (0.0,) * 1535
    async def fake_index(request):
        return ai.IndexRecordResult(chunks=(ai.IndexedChunk(text='숙소 예약 확인', location=ai.SourceLocation(label='2행'), block_indexes=(0,), embedding=vector),))
    monkeypatch.setattr(ai, 'index_record', fake_index)
    original_find = nodes.find_chunks
    async def embed(_texts):
        return [list(vector)]
    async def find(request, *, port):
        return await original_find(request, port=port, embed=embed)
    monkeypatch.setattr(nodes, 'find_chunks', find)
    headers, club_id = _owner_with_club(client)
    other, other_club = _owner_with_club(client)
    mine = _upload(client, headers, club_id, 'ETC', '숙소.csv')
    _upload(client, other, other_club, 'ETC', 'other.csv')
    response = client.get('/api/v1/records/search', headers=headers, params={'clubId': club_id, 'query':'숙소'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['semanticStatus'] == 'AVAILABLE' and data['indexedCount'] == 1
    assert response.json()['meta']['totalCount'] == 1
    item = data['items'][0]
    assert item['id'] == mine and item['matchTypes'] == ['FILENAME', 'SEMANTIC']
    assert item['excerpts'][0]['location']['label'] == '2행'
    async def unavailable(request, *, port):
        raise ai.AIConfigError('fixture')
    monkeypatch.setattr(nodes, 'find_chunks', unavailable)
    response = client.get('/api/v1/records/search', headers=headers, params={'clubId': club_id, 'query':'숙소'})
    assert response.status_code == 200
    assert response.json()['data']['semanticStatus'] == 'UNAVAILABLE'
    assert response.json()['data']['items'][0]['matchTypes'] == ['FILENAME']


async def test_토리_자료검색_실제DB_및_AI오류(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    from app.core.config import get_settings
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    async def no_index(_request):
        raise ai.AIConfigError('fixture')
    async def classify(_request):
        return ai.ToriIntentResult(intent='record_search', query='예산')
    monkeypatch.setattr(ai, 'index_record', no_index)
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, 'ETC', '예산.csv')
    res = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers, json={'message':'예산 자료'})
    assert res.status_code == 200, res.text
    data = res.json()['data']
    assert data['recordTotalCount'] == 1 and data['records']['items'][0]['fileName'] == '예산.csv'
    assert data['records']['semanticStatus'] == 'NO_INDEXED_RECORDS'
    async def fail(_request):
        raise ai.AIConfigError('fixture')
    monkeypatch.setattr(ai, 'classify_tori_intent', fail)
    res = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers, json={'message':'예산 자료'})
    assert res.status_code == 500 and res.json()['error']['code'] == 'AI_MISCONFIGURED'
