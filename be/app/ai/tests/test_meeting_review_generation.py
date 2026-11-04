import asyncio
import pytest
import app.ai as ai
from app.ai.features.meeting import review

def request():
    return ai.MeetingReviewRequest(transcripts=(ai.ReviewTranscript(segment_id='s1', text='회장이 민수가 예약하자고 했어요.', speaker_label='SPEAKER_00', speaker_name='지민'),))
def test_review_preserves_evidence_and_separates_assignee(monkeypatch):
    async def invoke(messages, schema):
        return schema.model_validate({'summary': [{'text':'장소 예약을 논의함','evidence_segment_ids':['s1']}], 'tasks':[{'title':'장소 예약','suggested_assignee':'민수','evidence_segment_ids':['s1']}]})
    monkeypatch.setattr(review, 'ainvoke_structured', invoke)
    result = asyncio.run(ai.generate_meeting_review(request()))
    assert result.tasks[0].suggested_assignee == '민수'
    assert result.tasks[0].evidence_segment_ids == ('s1',)
def test_review_rejects_unknown_evidence(monkeypatch):
    async def invoke(messages, schema):
        return schema.model_validate({'summary':[{'text':'없는 근거','evidence_segment_ids':['s9']}], 'tasks':[]})
    monkeypatch.setattr(review, 'ainvoke_structured', invoke)
    with pytest.raises(ai.AIInvalidResponseError):
        asyncio.run(ai.generate_meeting_review(request()))
