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
    assert data['recordAnswer']['status'] == 'insufficient'
    assert data['recordAnswer']['unindexedCount'] >= 1
    async def fail(_request):
        raise ai.AIConfigError('fixture')
    monkeypatch.setattr(ai, 'classify_tori_intent', fail)
    res = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers, json={'message':'예산 자료'})
    assert res.status_code == 500 and res.json()['error']['code'] == 'AI_MISCONFIGURED'

async def test_토리_원문청크_소속제한_출처와_생성실패(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    from app.ai.features.retrieval import nodes
    from app.core.config import get_settings
    from app.ai.contracts import RecordFact, RecordConflict

    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    vector = (1.0,) + (0.0,) * 1535
    long_text = '예산 원문 ' + '가' * 400

    async def index(request):
        return ai.IndexRecordResult(chunks=(ai.IndexedChunk(
            text=long_text, location=ai.SourceLocation(label='2행'),
            block_indexes=(0,), embedding=vector),))
    async def classify(_request):
        return ai.ToriIntentResult(intent='record_search', query='예산')
    original_find = nodes.find_chunks
    async def embed(_texts):
        return [list(vector)]
    async def find(request, *, port):
        return await original_find(request, port=port, embed=embed)
    captured = []
    async def answer(request):
        captured.extend(request.chunks)
        assert request.question == '예산 내용을 요약해줘'
        assert len(request.chunks) == 1 and request.chunks[0].text == long_text
        source = request.chunks[0].source
        one = RecordFact(content='30만 원', sources=(source,))
        two = RecordFact(content='40만 원', sources=(source,))
        return ai.ToriRecordAnswerResult(status='partial', facts=(one,),
            conflicts=(RecordConflict(description='예산 차이', values=(one, two)),),
            not_found=('최종 승인 여부',))
    monkeypatch.setattr(ai, 'index_record', index)
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr(nodes, 'find_chunks', find)
    monkeypatch.setattr(ai, 'answer_tori_records', answer)
    headers, club_id = _owner_with_club(client)
    other, other_club = _owner_with_club(client)
    mine = _upload(client, headers, club_id, 'ETC', '예산.csv')
    _upload(client, other, other_club, 'ETC', '다른소속.csv')
    url = f'/api/v1/clubs/{club_id}/tori/messages'
    response = client.post(url, headers=headers, json={'message':'예산 내용을 요약해줘'})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['recordAnswer']['status'] == 'partial'
    assert data['recordAnswer']['facts'][0]['sources'][0]['recordId'] == mine
    assert data['recordAnswer']['conflicts'][0]['values'][1]['text'] == '40만 원'
    assert data['recordAnswer']['notFound'] == ['최종 승인 여부']
    assert data['recordAnswer']['searchedChunkCount'] == 1
    assert data['records']['items'][0]['id'] == mine
    assert client.post(url, headers=other, json={'message':'예산 내용을 요약해줘'}).status_code == 403
    async def fail(_request):
        raise ai.AIRetryableError('private internal error')
    monkeypatch.setattr(ai, 'answer_tori_records', fail)
    failed = client.post(url, headers=headers, json={'message':'예산 내용을 요약해줘'}).json()['data']
    assert failed['recordAnswer']['status'] == 'failed'
    assert failed['records']['items'][0]['id'] == mine
    assert 'private internal error' not in str(failed)
    async def capped(_request, *, records):
        return tuple(captured[:1] * 50)
    async def no_evidence(_request):
        return ai.ToriRecordAnswerResult(status='no_evidence', not_found=('찾지 못함',))
    monkeypatch.setattr(ai, 'search_related_records', capped)
    monkeypatch.setattr(ai, 'answer_tori_records', no_evidence)
    limited = client.post(url, headers=headers, json={'message':'예산 내용을 요약해줘'}).json()['data']
    assert limited['recordAnswer']['status'] == 'insufficient'
    assert limited['recordAnswer']['candidateLimitReached'] is True
    async def search_fails(_request, *, records):
        raise ai.AIRetryableError('search failed')
    monkeypatch.setattr(ai, 'search_related_records', search_fails)
    degraded = client.post(url, headers=headers, json={'message':'예산 내용을 요약해줘'}).json()['data']
    assert degraded['recordAnswer']['status'] == 'failed'
    assert degraded['recordAnswer']['semanticStatus'] == 'UNAVAILABLE'
    assert degraded['records']['items'][0]['id'] == mine

async def test_토리_모델_호출_중_권한상실은_결과를_반환하지_않는다(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    import app.core.deps as deps
    from app.ai.features.retrieval import nodes
    from app.core.config import get_settings
    from app.core.exceptions import Forbidden
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    vector = (1.0,) + (0.0,) * 1535
    async def index(request):
        return ai.IndexRecordResult(chunks=(ai.IndexedChunk(text='예산 30만원',
            location=ai.SourceLocation(label='2행'), block_indexes=(0,), embedding=vector),))
    async def classify(_request):
        return ai.ToriIntentResult(intent='record_search', query='예산')
    original_find = nodes.find_chunks
    async def embed(_texts):
        return [list(vector)]
    async def find(request, *, port):
        return await original_find(request, port=port, embed=embed)
    original_ensure = deps.ensure_member
    revoked = False
    async def ensure(*args, **kwargs):
        if revoked:
            raise Forbidden()
        return await original_ensure(*args, **kwargs)
    async def answer(request):
        nonlocal revoked
        revoked = True
        return ai.ToriRecordAnswerResult(status='no_evidence', not_found=('없음',))
    monkeypatch.setattr(ai, 'index_record', index)
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr(nodes, 'find_chunks', find)
    monkeypatch.setattr(ai, 'answer_tori_records', answer)
    monkeypatch.setattr(deps, 'ensure_member', ensure)
    headers, club_id = _owner_with_club(client)
    _upload(client, headers, club_id, 'ETC', '예산.csv')
    response = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers,
                           json={'message':'예산'})
    assert response.status_code == 403
    assert '예산 30만원' not in response.text

async def test_토리_미색인_본문일치만_원문근거에_포함한다(client, app_db, monkeypatch, tmp_path):
    import app.ai as ai
    from app.ai.contracts import RecordFact
    from app.core.config import get_settings
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    get_settings.cache_clear()
    async def no_index(_request):
        raise ai.AIConfigError('fixture')
    async def classify(_request):
        return ai.ToriIntentResult(intent='record_search', query='예산')
    async def answer(request):
        assert len(request.chunks) == 1
        chunk = request.chunks[0]
        assert chunk.text == '항목: 예산, 금액: 300000'
        return ai.ToriRecordAnswerResult(status='answered', facts=(
            RecordFact(content='예산 300000', sources=(chunk.source,)),))
    monkeypatch.setattr(ai, 'index_record', no_index)
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr(ai, 'answer_tori_records', answer)
    headers, club_id = _owner_with_club(client)
    other, other_club = _owner_with_club(client)
    def upload(headers, club, filename, content):
        response = client.post('/api/v1/records', headers=headers,
            data={'clubId': club, 'category':'ETC'},
            files={'file': (filename, content.encode(), 'text/csv')})
        assert response.status_code == 201, response.text
        return response.json()['data']['id']
    mine = upload(headers, club_id, '내역.csv', '항목,금액\n예산,300000\n')
    filename_only = upload(headers, club_id, '예산.csv', '항목,금액\n간식,100\n')
    upload(other, other_club, '비밀.csv', '항목,금액\n예산,900000\n')
    response = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers,
                           json={'message':'예산은 얼마야?'})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert {item['id'] for item in data['records']['items']} == {mine, filename_only}
    assert data['recordAnswer']['status'] == 'answered'
    assert data['recordAnswer']['semanticStatus'] == 'NO_INDEXED_RECORDS'
    assert data['recordAnswer']['unindexedCount'] == 2
    assert data['recordAnswer']['lexicalChunkCount'] == 1
    assert data['recordAnswer']['filenameOnlyUnanalyzedCount'] == 1
    assert data['recordAnswer']['facts'][0]['sources'][0]['recordId'] == mine
    vector = (1.0,) + (0.0,) * 1535
    async def index(request):
        return ai.IndexRecordResult(chunks=(ai.IndexedChunk(text='기타',
            location=ai.SourceLocation(label='2행'), block_indexes=(0,), embedding=vector),))
    async def search_fails(_request, *, records):
        raise ai.AIRetryableError('fixture')
    monkeypatch.setattr(ai, 'index_record', index)
    monkeypatch.setattr(ai, 'search_related_records', search_fails)
    upload(headers, club_id, '기타.csv', '항목,금액\n기타,100\n')
    degraded = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers,
                           json={'message':'예산은 얼마야?'}).json()['data']
    assert degraded['recordAnswer']['status'] == 'partial'
    assert degraded['recordAnswer']['semanticStatus'] == 'UNAVAILABLE'
    assert degraded['recordAnswer']['facts'][0]['sources'][0]['recordId'] == mine
    monkeypatch.setattr(ai, 'index_record', no_index)
    upload(headers, club_id, '큰자료.csv', '항목,금액\n예산' + ('가' * 4100) + ',5\n')
    limited = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers,
                          json={'message':'예산은 얼마야?'}).json()['data']
    assert limited['recordAnswer']['lexicalOmitted'] is True
    assert limited['recordAnswer']['lexicalChunkCount'] == 1

async def test_토리_상한으로_제외된_의미청크는_권한재검증_대상에서_제외한다(client, app_db, monkeypatch):
    import app.ai as ai
    from app.ai.contracts import RecordFact
    from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
    from app.models.records import Record

    headers, club_id = _owner_with_club(client)
    async with db_session.get_sessionmaker()() as session:
        lexical = [Record(club_id=club_id, file_name=f'키워드{i}.csv',
            file_type=RecordFileType.CSV, category=RecordCategory.ETC,
            storage_key=f'lex-{i}', size=1, parse_status=RecordParseStatus.COMPLETED,
            parse_result={'blocks': [{'text': f'예산 {i}', 'location': {'label': '2행'}}]})
            for i in range(20)]
        semantic = [Record(club_id=club_id, file_name=f'semantic{i}.csv',
            file_type=RecordFileType.CSV, category=RecordCategory.ETC,
            storage_key=f'sem-{i}', size=1, parse_status=RecordParseStatus.INDEXED,
            parse_result={'blocks': [{'text': f'값 {i}', 'location': {'label': '2행'}}]})
            for i in range(40)]
        session.add_all(lexical + semantic)
        await session.flush()
        chunks = tuple(ai.RetrievedChunk(text=f'값 {i}',
            source=ai.RecordSource(record_id=record.id, file_name=record.file_name,
                                   location=ai.SourceLocation(label='2행')),
            category=RecordCategory.ETC, score=0.5) for i, record in enumerate(semantic))
        await session.commit()
    async def classify(_request):
        return ai.ToriIntentResult(intent='record_search', query='예산')
    async def search(_request, *, records):
        return chunks
    async def answer(request):
        assert len(request.chunks) == 50
        assert len({chunk.source.record_id for chunk in request.chunks}) == 50
        return ai.ToriRecordAnswerResult(status='answered', facts=(
            RecordFact(content='예산 확인', sources=(request.chunks[0].source,)),))
    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr(ai, 'search_related_records', search)
    monkeypatch.setattr(ai, 'answer_tori_records', answer)
    response = client.post(f'/api/v1/clubs/{club_id}/tori/messages', headers=headers,
                           json={'message': '예산 확인해줘'})
    assert response.status_code == 200, response.text
    answer_data = response.json()['data']['recordAnswer']
    assert answer_data['status'] == 'answered'
    assert answer_data['searchedChunkCount'] == 50
    assert answer_data['candidateLimitReached'] is True
    assert answer_data['lexicalChunkCount'] == 20
