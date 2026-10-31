"""자료함 공개 경계: 검색 범위, 원문 출처, 빈 결과와 실패를 확인한다."""
import asyncio

import pytest
from pydantic import ValidationError

from app.ai import (AIConfigError, RecordDiscoveryRequest, RecordSource, RetrievedChunk,
                    SourceLocation, search_related_records)
from app.ai.features.retrieval import nodes
from app.core.enums import RecordCategory


class Port:
    def __init__(self, result=()):
        self.result = result
        self.requests = []

    async def search_chunks(self, query):
        self.requests.append(query)
        return self.result


def run(coro):
    return asyncio.run(coro)


def test_search_uses_query_and_scope_and_returns_original_sources(monkeypatch):
    original = nodes.find_chunks
    seen = []
    async def embed(texts):
        seen.extend(texts)
        return [[1.0] + [0.0] * 1535]
    async def find(request, *, port):
        return await original(request, port=port, embed=embed)
    monkeypatch.setattr(nodes, 'find_chunks', find)
    chunk = RetrievedChunk(text='숙소 예산 20만원', category=RecordCategory.ETC, score=.8,
        source=RecordSource(record_id='r1', file_name='예산.csv', location=SourceLocation(label='2행')))
    port = Port((chunk,))
    result = run(search_related_records(RecordDiscoveryRequest(club_id='club', query='숙소 예산', limit=7), records=port))
    assert result == (chunk,) and seen == ['숙소 예산']
    assert port.requests[0].club_id == 'club' and port.requests[0].limit == 7
    assert len(port.requests[0].embedding) == 1536


def test_empty_result_and_embedding_failure_are_distinct(monkeypatch):
    original = nodes.find_chunks
    async def embed(texts):
        return [[1.0] + [0.0] * 1535]
    async def find(request, *, port):
        return await original(request, port=port, embed=embed)
    monkeypatch.setattr(nodes, 'find_chunks', find)
    request = RecordDiscoveryRequest(club_id='club', query='행사')
    assert run(search_related_records(request, records=Port())) == ()
    async def fail(request, *, port):
        raise AIConfigError('설정 없음')
    monkeypatch.setattr(nodes, 'find_chunks', fail)
    with pytest.raises(AIConfigError):
        run(search_related_records(request, records=Port()))


@pytest.mark.parametrize('fields', [dict(club_id='', query='행사'), dict(club_id='c', query='  '),
                                    dict(club_id='c', query='행사', limit=51)])
def test_invalid_search_input_is_rejected(fields):
    with pytest.raises(ValidationError):
        RecordDiscoveryRequest(**fields)


def test_port_failure_is_not_reported_as_empty(monkeypatch):
    original = nodes.find_chunks
    async def embed(texts):
        return [[1.0] + [0.0] * 1535]
    async def find(request, *, port):
        return await original(request, port=port, embed=embed)
    class BrokenPort:
        async def search_chunks(self, query):
            raise RuntimeError('검색 저장소 실패')
    monkeypatch.setattr(nodes, 'find_chunks', find)
    with pytest.raises(RuntimeError, match='검색 저장소 실패'):
        run(search_related_records(RecordDiscoveryRequest(club_id='club', query='행사'), records=BrokenPort()))
