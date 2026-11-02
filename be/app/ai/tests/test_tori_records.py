"""토리 답은 전달된 근거의 숫자와 출처를 확인하고 실패를 숨기지 않는다."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from app.ai import (AIInvalidResponseError, RecordSource, RetrievedChunk, SourceLocation,
                    ToriRecordAnswerRequest, answer_tori_records)
from app.ai.contracts import RecordConflict, RecordFact, RecordSearchResult
from app.ai.features.tori import records
from app.core.enums import RecordCategory


def chunk(text='총 예산 600,000원. 재료비 220,000원', name='예산.csv'):
    return RetrievedChunk(text=text, source=RecordSource(record_id=name, file_name=name,
        location=SourceLocation(label='1행')), category=RecordCategory.ETC, score=.8)


def request(chunks, question='행사 예산을 정리해줘'):
    return ToriRecordAnswerRequest(question=question, today='2026-11-03', chunks=chunks)


def run(req):
    return asyncio.run(answer_tori_records(req))


def test_grounded_facts_and_missing_are_separately_returned(monkeypatch):
    c = chunk()
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='총 예산 600,000원', sources=(c.source,)),), not_found=('세부 내역',))))
    result = run(request((c,)))
    assert result.status == 'partial' and result.facts[0].sources == (c.source,)
    assert result.not_found == ('세부 내역',)


def test_unsupported_number_and_query_year_are_not_reported_as_facts(monkeypatch):
    c = chunk()
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='총 예산 700,000원', sources=(c.source,)),))))
    assert run(request((c,))).status == 'no_evidence'
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='총 예산 600,000원', sources=(c.source,)),))))
    assert run(request((c,), '2025년 행사 예산')).status == 'no_evidence'


def test_year_in_source_and_numeric_conflicts_keep_per_fact_sources(monkeypatch):
    a, b = chunk('회비 20,000원', '2025_장부.csv'), chunk('회비 30,000원', '2025_회의록.csv')
    conflict = RecordConflict(description='회비 차이', values=(
        RecordFact(content='회비 20,000원', sources=(a.source,)),
        RecordFact(content='회비 30,000원', sources=(b.source,))))
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(conflicts=(conflict,))))
    result = run(request((a, b), '2025년 회비'))
    assert result.status == 'answered' and result.conflicts == (conflict,)


def test_empty_does_not_call_model_and_failure_propagates(monkeypatch):
    mock = AsyncMock(side_effect=AIInvalidResponseError('실패'))
    monkeypatch.setattr(records, 'assess_chunks', mock)
    assert run(request(())).status == 'no_evidence'
    mock.assert_not_awaited()
    with pytest.raises(AIInvalidResponseError):
        run(request((chunk(),)))


def test_numbers_in_filenames_and_unsupported_units_are_not_proof(monkeypatch):
    c = chunk('준비 내용은 숙소 예약입니다.', '예산600000원.csv')
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='총 예산 600000원', sources=(c.source,)),))))
    assert run(request((c,))).status == 'no_evidence'
    c = chunk('예산 22만원')
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='예산 22억원', sources=(c.source,)),))))
    assert run(request((c,))).status == 'no_evidence'


def test_facts_with_unprovided_sources_are_not_returned(monkeypatch):
    c, other = chunk(), chunk(name='다른자료.csv')
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(
        facts=(RecordFact(content='예산 600,000원', sources=(other.source,)),))))
    assert run(request((c,))).status == 'no_evidence'


def test_unsupported_calculation_or_decimal_is_partial(monkeypatch):
    c = chunk('예산 10.5만원과 2.5만원')
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(facts=(
        RecordFact(content='예산 10.5만원', sources=(c.source,)),
        RecordFact(content='합계 13만원', sources=(c.source,)),))))
    result = run(request((c,)))
    assert result.status == 'partial' and len(result.facts) == 1 and result.not_found


def test_conflict_with_unsupported_value_is_excluded(monkeypatch):
    a, b = chunk('회비 20,000원'), chunk('회비 30,000원', '회의록.csv')
    conflict = RecordConflict(description='회비 차이', values=(
        RecordFact(content='회비 20,000원', sources=(a.source,)),
        RecordFact(content='회비 90,000원', sources=(b.source,))))
    monkeypatch.setattr(records, 'assess_chunks', AsyncMock(return_value=RecordSearchResult(conflicts=(conflict,))))
    assert run(request((a, b))).status == 'no_evidence'
