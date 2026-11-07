import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

import app.ai as ai
from app.ai.features.meeting import event_intent


def request(text):
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    return ai.JudgeUtteranceRequest(meeting_id='m', club_id='c', utterance=ai.MeetingUtterance(
        utterance_id='u', seq=1, text=text, started_at=now, ended_at=now))


@pytest.mark.parametrize(('text', 'payload'), [
    ('지금 진행 중인 행사 장소와 예상 인원?', dict(disposition='lookup', scope='current', fields=['location', 'expected_headcount'], event_reference=None)),
    ('최근 행사 실제 참가 인원?', dict(disposition='lookup', scope='recent', fields=['actual_headcount'], event_reference=None)),
    ('2025 봄 MT 날짜는?', dict(disposition='lookup', scope='selected', fields=['dates'], event_reference='2025 봄 MT')),
    ('작년 MT 예산은?', dict(disposition='none', scope=None, fields=[], event_reference=None)),
    ('행사 인원 몇 명?', dict(disposition='clarify', scope=None, fields=[], event_reference=None)),
])
def test_public_classification_preserves_input_and_trace(monkeypatch, text, payload):
    async def invoke(messages, schema, *, model):
        assert text in messages[1].content
        assert '예상 인원과 실제 참가 인원' in messages[0].content
        return schema.model_validate(payload)
    monkeypatch.setattr(event_intent, 'get_judge_model', lambda: object())
    monkeypatch.setattr(event_intent, 'ainvoke_structured', invoke)
    result = asyncio.run(ai.classify_meeting_event_facts(request(text)))
    assert result.intent.disposition == payload['disposition']
    assert result.intent.scope == payload['scope']
    assert result.intent.fields == tuple(payload['fields'])
    assert result.trace.prompt_version == 'meeting-event-facts-v1'
    assert result.trace.judge_ms >= 0


def test_invalid_intents_and_model_error_are_not_silent(monkeypatch):
    with pytest.raises(ValidationError):
        ai.MeetingEventIntent(disposition='lookup', scope='selected', fields=['status'], event_reference=None)
    with pytest.raises(ValidationError):
        ai.MeetingEventIntent(disposition='none', scope='current', fields=[], event_reference=None)
    async def failure(messages, schema, *, model):
        raise ai.AIRetryableError('실패')
    monkeypatch.setattr(event_intent, 'get_judge_model', lambda: object())
    monkeypatch.setattr(event_intent, 'ainvoke_structured', failure)
    with pytest.raises(ai.AIRetryableError) as raised:
        asyncio.run(ai.classify_meeting_event_facts(request('최근 행사는?')))
    assert raised.value.trace.prompt_version == 'meeting-event-facts-v1'


def test_invented_event_reference_is_rejected(monkeypatch):
    async def invoke(messages, schema, *, model):
        return schema(disposition='lookup', scope='selected', fields=['status'], event_reference='2025 봄 MT')
    monkeypatch.setattr(event_intent, 'get_judge_model', lambda: object())
    monkeypatch.setattr(event_intent, 'ainvoke_structured', invoke)
    with pytest.raises(ai.AIInvalidResponseError):
        asyncio.run(ai.classify_meeting_event_facts(request('그 행사 상태는?')))
