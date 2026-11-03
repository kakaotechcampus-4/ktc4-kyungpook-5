"""토리 답은 모델이 지정한 청크의 숫자와 출처를 확인한다."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from app.ai import (AIInvalidResponseError, RecordSource, RetrievedChunk, SourceLocation,
                    ToriRecordAnswerRequest, answer_tori_records)
from app.ai.features.retrieval import nodes
from app.ai.features.retrieval.schemas import EvidenceAssessment, EvidenceConflict, EvidenceItem
from app.core.enums import RecordCategory


def chunk(text='총 예산 600,000원. 재료비 220,000원', name='예산.csv'):
    return RetrievedChunk(text=text, source=RecordSource(record_id=name, file_name=name,
        location=SourceLocation(label='1행')), category=RecordCategory.ETC, score=.8)


def run(chunks, question='행사 예산을 정리해줘'):
    return asyncio.run(answer_tori_records(ToriRecordAnswerRequest(question=question, today='2026-11-03', chunks=chunks)))


def item(content, *ids):
    return EvidenceItem(content=content, chunk_ids=list(ids))


def mock_assessment(monkeypatch, *, facts=(), conflicts=(), not_found=()):
    assessment = EvidenceAssessment(sufficient=True, retry_queries=[], facts=list(facts),
                                    conflicts=list(conflicts), not_found=list(not_found))
    monkeypatch.setattr(nodes, 'assess', AsyncMock(return_value={'assessment': assessment}))


def test_grounded_facts_and_missing(monkeypatch):
    c = chunk()
    mock_assessment(monkeypatch, facts=[item('총 예산 600,000원', 'c1')], not_found=['세부 내역'])
    result = run((c,))
    assert result.status == 'partial' and result.facts[0].sources == (c.source,)
    assert result.not_found == ('세부 내역',)


def test_unsupported_number_and_year(monkeypatch):
    c = chunk()
    mock_assessment(monkeypatch, facts=[item('총 예산 700,000원', 'c1')])
    assert run((c,)).status == 'no_evidence'
    mock_assessment(monkeypatch, facts=[item('총 예산 600,000원', 'c1')])
    assert run((c,), '2025년 행사 예산').status == 'no_evidence'


def test_year_in_source_and_conflicts(monkeypatch):
    a, b = chunk('회비 20,000원', '2025_장부.csv'), chunk('회비 30,000원', '2025_회의록.csv')
    conflict = EvidenceConflict(description='회비 차이', values=[item('회비 20,000원', 'c1'), item('회비 30,000원', 'c2')])
    mock_assessment(monkeypatch, conflicts=[conflict])
    result = run((a, b), '2025년 회비')
    assert result.status == 'answered'
    assert [v.sources for v in result.conflicts[0].values] == [(a.source,), (b.source,)]


def test_empty_and_failure(monkeypatch):
    mock = AsyncMock(side_effect=AIInvalidResponseError('실패'))
    monkeypatch.setattr(nodes, 'assess', mock)
    assert run(()).status == 'no_evidence'
    mock.assert_not_awaited()
    with pytest.raises(AIInvalidResponseError):
        run((chunk(),))


def test_filename_numbers_and_units(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('총 예산 600000원', 'c1')])
    assert run((chunk('숙소 예약', '예산600000원.csv'),)).status == 'no_evidence'
    mock_assessment(monkeypatch, facts=[item('예산 22억원', 'c1')])
    assert run((chunk('예산 22만원'),)).status == 'no_evidence'


@pytest.mark.parametrize('ids', [('c99',), ()])
def test_invalid_citation_is_not_hidden(monkeypatch, ids):
    mock_assessment(monkeypatch, facts=[item('예산 900원', *ids)])
    with pytest.raises(AIInvalidResponseError):
        run((chunk(),))


def test_calculation_or_decimal_is_partial(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('예산 10.5만원', 'c1'), item('합계 13만원', 'c1')])
    result = run((chunk('예산 10.5만원과 2.5만원'),))
    assert result.status == 'partial' and len(result.facts) == 1 and result.not_found


def test_conflict_with_unsupported_value(monkeypatch):
    a, b = chunk('회비 20,000원'), chunk('회비 30,000원', '회의록.csv')
    conflict = EvidenceConflict(description='회비 차이', values=[item('회비 20,000원', 'c1'), item('회비 90,000원', 'c2')])
    mock_assessment(monkeypatch, conflicts=[conflict])
    assert run((a, b)).status == 'no_evidence'


def test_same_source_does_not_mix_unquoted_chunk_numbers(monkeypatch):
    a, b = chunk('홍보비 100원'), chunk('숙박비 200원')
    assert a.source == b.source
    mock_assessment(monkeypatch, facts=[item('홍보비 200원', 'c1'), item('숙박비 200원', 'c2')])
    result = run((a, b))
    assert result.status == 'partial' and [f.content for f in result.facts] == ['숙박비 200원']
    mock_assessment(monkeypatch, conflicts=[EvidenceConflict(description='차이', values=[
        item('홍보비 200원', 'c1'), item('숙박비 200원', 'c2')])])
    assert run((a, b)).status == 'no_evidence'


@pytest.mark.parametrize('question', ['2025에 MT 담당자는?', '2025년 MT 담당자는?'])
def test_year_with_particle(monkeypatch, question):
    mock_assessment(monkeypatch, facts=[item('담당자는 민수', 'c1')])
    assert run((chunk('2024년 MT 담당자는 민수'),), question).status == 'no_evidence'


@pytest.mark.parametrize('question', ['2025원 예산은?', '2025 원 예산은?', '2025만원 예산은?'])
def test_amount_is_not_year(monkeypatch, question):
    mock_assessment(monkeypatch, facts=[item('예산은 2025원', 'c1')])
    assert run((chunk('예산은 2025원'),), question).status == 'answered'


@pytest.mark.parametrize('question', [
    '2023년부터 2025년까지 가을 MT를 요약해줘',
    '2023~2025년 가을 MT를 요약해줘',
])
@pytest.mark.parametrize(('year', 'expected'), [
    (2022, 'no_evidence'), (2023, 'answered'), (2024, 'answered'),
    (2025, 'answered'), (2026, 'no_evidence'),
])
def test_requested_year_range_includes_only_in_range_sources(monkeypatch, question, year, expected):
    mock_assessment(monkeypatch, facts=[item(f'{year}년 예산은 600000원', 'c1')])
    assert run((chunk(f'{year}년 총 예산 600000원'),), question).status == expected


def test_explicit_follow_up_year_restricts_original_range(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('2024년 예산은 600000원', 'c1')])
    request = ToriRecordAnswerRequest(question='2023년부터 2025년 행사 예산',
        follow_up='2025년', today='2026-11-03', chunks=(chunk('2024년 총 예산 600000원'),))
    assert asyncio.run(answer_tori_records(request)).status == 'no_evidence'


def test_requested_year_cannot_be_bypassed_by_other_year_in_same_chunk(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('2026년 예산은 600000원', 'c1')])
    assert run((chunk('2024년과 2026년 총 예산 600000원'),), '2023~2025년 예산').status == 'no_evidence'


@pytest.mark.parametrize(('source', 'claim', 'expected'), [
    ('잔액 -100,000원', '잔액 100,000원', 'no_evidence'),
    ('잔액 100,000원', '잔액 -100,000원', 'no_evidence'),
    ('잔액 -100,000원', '잔액 -100000원', 'answered'),
    ('잔액 −100,000원', '잔액 -100000원', 'answered'),
    ('잔액 +100,000원', '잔액 100000원', 'answered'),
    ('증감 -1.5%', '증감 1.5%', 'no_evidence'),
    ('잔액 -₩100,000', '잔액 ₩100,000', 'no_evidence'),
    ('잔액 ₩100,000', '잔액 -₩100,000', 'no_evidence'),
    ('잔액 ₩−100,000', '잔액 -100000원', 'answered'),
    ('잔액 ₩+100,000', '잔액 100000원', 'answered'),
    ('잔액 -₩100,000', '잔액 ₩-100000', 'answered'),
    ('잔액 - 100,000원', '잔액 100,000원', 'no_evidence'),
    ('잔액 마이너스 100,000원', '잔액 100,000원', 'no_evidence'),
    ('잔액 음수 100,000원', '잔액 -100,000원', 'answered'),
])
def test_evidence_amount_sign_is_preserved(monkeypatch, source, claim, expected):
    mock_assessment(monkeypatch, facts=[item(claim, 'c1')])
    assert run((chunk(source),)).status == expected


@pytest.mark.parametrize(('source', 'claim', 'expected'), [
    ('잔액 (100,000원)', '잔액 100,000원', 'no_evidence'),
    ('잔액 (₩100,000)', '잔액 ₩100,000', 'no_evidence'),
    ('잔액 ₩(100,000)', '잔액 -100,000원', 'no_evidence'),
    ('잔액 100,000원', '잔액 (₩100,000)', 'no_evidence'),
    ('잔액 (₩-100,000)', '잔액 -100,000원', 'answered'),
    ('잔액 (100,000원)', '잔액 -100,000원', 'no_evidence'),
    ('잔액 100,000원', '잔액 (100,000원)', 'no_evidence'),
    ('잔액 (-100,000원)', '잔액 -100000원', 'answered'),
    ('총예산 1,000원', '총예산 백만원', 'no_evidence'),
    ('총예산 백만원', '총예산 백만원', 'answered'),
    ('총예산 10 만원', '총예산 만원', 'no_evidence'),
    ('총예산 10 만원', '총예산 10만원', 'answered'),
    ('총예산 2 백만원', '총예산 백만원', 'no_evidence'),
    ('잔액 -백만원', '잔액 백만원', 'no_evidence'),
    ('잔액 마이너스 백만원', '잔액 백만원', 'no_evidence'),
    ('잔액 마이너스 백만원', '잔액 -백만원', 'answered'),
    ('참가자 1명', '참가자 한 명', 'no_evidence'),
    ('참가자 한 명', '참가자 한명', 'answered'),
    ('참가자 20명', '참가자 스무 명', 'no_evidence'),
])
def test_ambiguous_or_korean_quantities_require_matching_evidence(monkeypatch, source, claim, expected):
    mock_assessment(monkeypatch, facts=[item(claim, 'c1')])
    assert run((chunk(source),)).status == expected


def test_event_name_is_not_four_attendees_in_grounded_answer(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('연도와 행사명이 기재되지 않은 행사 총예산은 600000원이다.', 'c1')])
    assert run((chunk('행사 총예산 600,000원'),)).status == 'answered'


@pytest.mark.parametrize('claim', ['참가자는 사명', '참가자는사명', '참가자사명', '참가자는총사명', '참가인원약사명', '행사명사명'])
def test_korean_people_quantity_is_still_checked(monkeypatch, claim):
    mock_assessment(monkeypatch, facts=[item(claim, 'c1')])
    assert run((chunk('참가자 3명'),)).status == 'no_evidence'
