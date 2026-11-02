"""범위 질문과 후속 답변은 토리 경계에서만 처리한다."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from app.ai import (AIInvalidResponseError, ToriRecordAnswerRequest, ToriRecordQueryRequest,
                    ToriRecordQueryResult, answer_tori_records, build_tori_record_query)
from app.ai.features.tori import records, query
from app.ai.features.retrieval.schemas import EvidenceItem
from app.ai.tests.test_tori_records import chunk


def assessment(**updates):
    data = dict(sufficient=True, retry_queries=[], facts=[], conflicts=[], not_found=[],
                clarification_question=None, clarification_options=[])
    data.update(updates)
    return records.ToriAssessment(**data)


def run_answer(monkeypatch, output, **kwargs):
    monkeypatch.setattr(records, 'ainvoke_structured', AsyncMock(return_value=output))
    req = ToriRecordAnswerRequest(question='행사 예산 자료', today='2026-11-03',
        chunks=(chunk('2024년 봄 MT 예산 100원'), chunk('2025년 봄 MT 예산 200원')), **kwargs)
    return asyncio.run(answer_tori_records(req))


def test_clarification_choices_are_grounded(monkeypatch):
    result = run_answer(monkeypatch, assessment(clarification_question='어느 연도를 볼까요?',
        clarification_options=[records.ToriOption(content='2024년', chunk_ids=['c1']),
                               records.ToriOption(content='2025년', chunk_ids=['c2']),
                               records.ToriOption(content='전체 요약', chunk_ids=[])]))
    assert result.status == 'clarification' and result.facts == ()
    assert result.clarification_options == ('2024년', '2025년', '전체 요약')


@pytest.mark.parametrize('options', [
    [records.ToriOption(content='2026년', chunk_ids=['c1']), records.ToriOption(content='전체 요약', chunk_ids=[])],
    [records.ToriOption(content='2024년', chunk_ids=['c99']), records.ToriOption(content='전체 요약', chunk_ids=[])],
    [records.ToriOption(content='2024년', chunk_ids=['c1']), records.ToriOption(content='2024년', chunk_ids=['c1'])],
])
def test_unsupported_clarification_choices_fail(monkeypatch, options):
    with pytest.raises(AIInvalidResponseError):
        run_answer(monkeypatch, assessment(clarification_question='어느 연도인가요?', clarification_options=options))


def test_follow_up_cannot_ask_again(monkeypatch):
    output = assessment(clarification_question='어느 연도인가요?', clarification_options=[
        records.ToriOption(content='2024년', chunk_ids=['c1']), records.ToriOption(content='전체 요약', chunk_ids=[])])
    with pytest.raises(AIInvalidResponseError):
        run_answer(monkeypatch, output, follow_up='잘 모르겠어', clarification_allowed=False)


def test_grouped_answer_keeps_source(monkeypatch):
    output = assessment(facts=[EvidenceItem(content='2025년 봄 MT 예산은 200원이다.', chunk_ids=['c2'])])
    result = run_answer(monkeypatch, output, follow_up='2025년 봄 MT', clarification_allowed=False)
    assert result.status == 'answered' and len(result.facts) == 1 and result.not_found == ()
    assert result.facts[0].sources[0].record_id == '예산.csv'


@pytest.mark.parametrize('data', [
    dict(disposition='follow_up', query=None), dict(disposition='new_request', query='예산'),
    dict(disposition='follow_up', query='x' * 201),
])
def test_query_result_validation(data):
    with pytest.raises(ValidationError):
        ToriRecordQueryResult(**data)


def test_query_model_receives_question_and_follow_up(monkeypatch):
    async def invoke(messages, schema):
        assert '행사 예산' in messages[-1].content and '2025년 봄 MT' in messages[-1].content
        return schema(disposition='follow_up', query='2025년 봄 MT 행사 예산')
    monkeypatch.setattr(query, 'ainvoke_structured', invoke)
    result = asyncio.run(build_tori_record_query(ToriRecordQueryRequest(
        question='행사 예산', follow_up='2025년 봄 MT')))
    assert result.disposition == 'follow_up' and '2025년' in result.query


def test_retry_gives_summary_without_second_question(monkeypatch):
    first = assessment(clarification_question='어느 연도인가요?', clarification_options=[
        records.ToriOption(content='2024년', chunk_ids=['c1']), records.ToriOption(content='전체 요약', chunk_ids=[])])
    second = assessment(facts=[EvidenceItem(content='2024년 봄 MT 예산은 100원이다.', chunk_ids=['c1'])])
    mock = AsyncMock(side_effect=[first, second])
    monkeypatch.setattr(records, 'ainvoke_structured', mock)
    request = ToriRecordAnswerRequest(question='행사 예산', follow_up='잘 모르겠어',
        clarification_allowed=False, today='2026-11-03', chunks=(chunk('2024년 봄 MT 예산 100원'),))
    result = asyncio.run(answer_tori_records(request))
    assert result.status == 'answered' and len(result.facts) == 1
    assert mock.await_count == 2


def test_clarification_lengths_match_public_contract():
    with pytest.raises(ValidationError):
        assessment(clarification_question='x' * 501)
    with pytest.raises(ValidationError):
        records.ToriOption(content='x' * 201, chunk_ids=['c1'])
    with pytest.raises(ValidationError):
        records.ToriRecordAnswerResult(status='clarification', clarification_question='x' * 501)
    with pytest.raises(ValidationError):
        records.ToriRecordAnswerResult(status='clarification', clarification_options=('x' * 201,))


def test_clarification_text_is_trimmed_and_not_blank():
    result = records.ToriRecordAnswerResult(status='clarification',
        clarification_question='  어느 연도인가요?  ', clarification_options=('  2025년  ',))
    assert result.clarification_question == '어느 연도인가요?' and result.clarification_options == ('2025년',)
    with pytest.raises(ValidationError):
        records.ToriOption(content='   ', chunk_ids=['c1'])


def test_year_option_can_be_supported_by_filename(monkeypatch):
    output = assessment(clarification_question='어느 연도를 볼까요?', clarification_options=[
        records.ToriOption(content='2025년 행사 예산', chunk_ids=['c1']),
        records.ToriOption(content='전체 요약', chunk_ids=[])])
    monkeypatch.setattr(records, 'ainvoke_structured', AsyncMock(return_value=output))
    request = ToriRecordAnswerRequest(question='행사 예산', today='2026-11-03',
        chunks=(chunk('식비 100원', '2025_예산.csv'),))
    result = asyncio.run(answer_tori_records(request))
    assert result.status == 'clarification' and result.clarification_options[0] == '2025년 행사 예산'




def test_query_prior_question_and_choices_are_passed(monkeypatch):
    async def invoke(messages, schema):
        prompt = messages[-1].content
        assert '어느 연도' in prompt and '2024년' in prompt and '2025년' in prompt and '첫 번째' in prompt
        return schema(disposition='follow_up', query='2024년 행사 예산')
    monkeypatch.setattr(query, 'ainvoke_structured', invoke)
    result = asyncio.run(build_tori_record_query(ToriRecordQueryRequest(
        question='행사 예산', follow_up='첫 번째', clarification_question='어느 연도?',
        clarification_options=('2024년', '2025년', '전체 요약'))))
    assert result.query == '2024년 행사 예산'


def test_answer_prior_question_and_choices_are_passed(monkeypatch):
    async def invoke(messages, schema):
        prompt = messages[-1].content
        assert '어느 연도' in prompt and '2025년' in prompt and '첫 번째' in prompt
        return assessment(facts=[EvidenceItem(content='2025년 봄 MT 예산 200원', chunk_ids=['c1'])])
    monkeypatch.setattr(records, 'ainvoke_structured', invoke)
    result = asyncio.run(answer_tori_records(ToriRecordAnswerRequest(
        question='행사 예산', follow_up='첫 번째', clarification_allowed=False,
        clarification_question='어느 연도?', clarification_options=('2025년', '전체 요약'),
        today='2026-11-03', chunks=(chunk('2025년 봄 MT 예산 200원'),))))
    assert result.status == 'answered'


@pytest.mark.parametrize('data', [
    {'clarification_question': 'x' * 501},
    {'clarification_options': ('x' * 201,)},
    {'clarification_options': ('하나', '둘', '셋', '넷')},
])
def test_prior_context_limits_apply_to_query_and_answer(data):
    with pytest.raises(ValidationError):
        ToriRecordQueryRequest(question='예산', follow_up='첫번째', **data)
    with pytest.raises(ValidationError):
        ToriRecordAnswerRequest(question='예산', today='2026-11-03', chunks=(), **data)
