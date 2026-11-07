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


# #281 멘토 리뷰: 장부 원문 "45000"과 답변 "45,000원"을 다른 숫자로 봐서 맞는 답이 사라졌다.
# 숫자는 값으로 읽고, 단위는 원문과 답변 양쪽에 다 있을 때만 같은지 본다.
@pytest.mark.parametrize(('source', 'claim'), [
    ('항목: 숙소비, 금액: 45000', '숙소비는 45,000원'),       # CSV 장부 칸
    ('항목: 숙소비, 금액: 45,000', '숙소비는 45000원'),       # ₩ 서식 XLSX 칸(파서가 ₩를 남기지 않음)
    ('금액: 45,000원', '숙소비는 45000'),
    ('금액: 45000\\', '숙소비는 45,000원'),                  # 숫자 뒤 \ 표시
    ('금액: 45,000 \\', '숙소비는 45,000원'),
    ('금액: \\45,000', '숙소비는 45,000원'),                 # 숫자 앞 \ 표시
    ('금액: 45,000₩', '숙소비는 ₩45,000'),
    ('금액: 45,000.00', '숙소비는 45,000원'),
    ('참가 인원: 40', '참가 인원은 40명'),
    ('금액: 10만원', '금액은 100,000원'),
    ('금액: 100,000원', '금액은 10만원'),
    ('금액: 45000', '숙소비는 4만 5천원'),
    ('예산 4.5만원', '예산 45,000원'),
    ('예산 1억 2천만원', '예산 120,000,000원'),
    ('예산 십만 원', '예산 100,000원'),
])
def test_same_value_in_other_notation_is_supported(monkeypatch, source, claim):
    mock_assessment(monkeypatch, facts=[item(claim, 'c1')])
    assert run((chunk(source),)).status == 'answered'


@pytest.mark.parametrize(('source', 'claim'), [
    ('금액: 45,000원', '숙소비는 45,000명'),     # 양쪽 단위가 다름
    ('금액: 45000', '숙소비는 46,000원'),        # 값이 다름
    ('잔액: -100000', '잔액은 100,000원'),       # 부호가 다름
    ('금액: $45', '금액은 45원'),                # 외화는 원 금액으로 통과하지 않음
    ('금액: 45달러', '금액은 45원'),
    ('예산 10만원과 2만원', '합계 12만원'),       # 합산은 하지 않음
    ('예산 1억 2천만원', '예산 10,000원'),        # "2천만원" 속 "만원"을 따로 세지 않음
    ('예산 5천 4만원', '예산 45,000원'),          # 큰 단위 순서가 어긋난 표기는 값으로 읽지 않음
    ('잔액 (45,000\\)', '잔액 45,000원'),        # 괄호 금액은 양·음이 모호해 근거에서 뺌
])
def test_different_value_or_unit_is_still_rejected(monkeypatch, source, claim):
    mock_assessment(monkeypatch, facts=[item(claim, 'c1')])
    assert run((chunk(source),)).status == 'no_evidence'


def test_amount_with_won_mark_after_is_not_a_year(monkeypatch):
    mock_assessment(monkeypatch, facts=[item('예산은 2025원', 'c1')])
    assert run((chunk('예산: 2025\\'),), '2025\\ 예산은?').status == 'answered'


def test_known_limit_unitless_number_of_other_item(monkeypatch):
    # 알려진 한계: 숫자 검사는 "어느 항목의 숫자인지"를 보지 않는다.
    # 원문의 인원 40에 단위가 없어서, 모델이 회비로 잘못 옮겨도 통과한다.
    mock_assessment(monkeypatch, facts=[item('회비는 40원', 'c1')])
    assert run((chunk('참가 인원: 40, 회비: 20000'),)).status == 'answered'
