"""토리 분류는 실행 없이 호출 범위와 모델 오류를 보존한다."""
import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from app.ai import AIConfigError, ToriIntentRequest, ToriIntentResult, classify_tori_intent
from app.ai.features.tori import intent


def test_public_intent_passes_message_and_returns_typed_result(monkeypatch):
    async def invoke(messages, schema):
        assert '이번 주 내 할 일' in messages[-1].content
        assert schema is ToriIntentResult
        return schema(intent='task_list', scope='self', kind='task',
                      date_from='2026-10-26', date_to='2026-11-01')
    monkeypatch.setattr(intent, 'ainvoke_structured', invoke)
    result = asyncio.run(classify_tori_intent(ToriIntentRequest(message='이번 주 내 할 일', reference_date='2026-10-30')))
    assert result.date_from == date(2026, 10, 26) and result.scope == 'self'


def test_model_failure_propagates(monkeypatch):
    async def invoke(*args):
        raise AIConfigError('설정 없음')
    monkeypatch.setattr(intent, 'ainvoke_structured', invoke)
    with pytest.raises(AIConfigError):
        asyncio.run(classify_tori_intent(ToriIntentRequest(message='자료 찾아줘', reference_date='2026-10-30')))


@pytest.mark.parametrize('data', [
    dict(intent='record_search'),
    dict(intent='meeting', query='자료'),
    dict(intent='unsupported', scope='all'),
    dict(intent='task_list', date_from='2026-11-01', date_to='2026-10-30'),
])
def test_inconsistent_output_is_rejected(data):
    with pytest.raises(ValidationError):
        ToriIntentResult(**data)


def test_invalid_timezone_is_rejected():
    with pytest.raises(ValidationError):
        ToriIntentRequest(message='안녕', reference_date='2026-10-30', timezone='Invalid/Zone')
