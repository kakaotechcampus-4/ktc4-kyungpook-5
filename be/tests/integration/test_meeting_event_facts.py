"""회의 행사 조회는 같은 동아리의 사실만 표시한다."""
from types import SimpleNamespace
import pytest
from app import ai
from app.core.enums import EventStatus
from app.db import session as db_session
from app.models.clubs import Club
from app.models.events import Event
from app.services import meeting_event_service

pytestmark = [pytest.mark.db, pytest.mark.anyio]

@pytest.fixture
async def app_db(migrated_db_url, monkeypatch, clear_db_caches):
    monkeypatch.setenv('DATABASE_URL', migrated_db_url)
    yield
    await db_session.get_engine().dispose()

def payload(club_id):
    return {'meeting_id': 'meeting', 'club_id': club_id, 'utterance': {
        'utterance_id': 'u', 'seq': 1, 'text': '진행 중 행사 예상 인원?',
        'started_at': '2026-11-04T10:00:00+09:00', 'ended_at': '2026-11-04T10:00:01+09:00'}}

async def test_current_scope_is_club_filtered_and_actual_unknown(app_db, monkeypatch):
    async def classify(request):
        return SimpleNamespace(intent=ai.MeetingEventIntent(disposition='lookup', scope='current',
            fields=('expected_headcount', 'actual_headcount'), event_reference=None), trace=ai.JudgeTrace(
            model='fake', prompt_version='fake', judge_ms=3))
    monkeypatch.setattr(ai, 'classify_meeting_event_facts', classify)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        one, other = Club(name='하나'), Club(name='다른 동아리')
        session.add_all([one, other]); await session.flush()
        session.add_all([Event(club_id=one.id, title='우리 행사', status=EventStatus.ON_GOING, expected_headcount=40),
                         Event(club_id=other.id, title='다른 행사', status=EventStatus.ON_GOING, expected_headcount=77)])
        await session.commit(); club_id = one.id
    result, _ = await meeting_event_service.answer(payload(club_id))
    assert '우리 행사' in result['answer'] and '예상 인원: 40명' in result['answer']
    assert '실제 참가 인원: 미확인' in result['answer'] and '다른 행사' not in result['answer']
    assert set(result['citations'][0]) == {'type', 'eventId', 'title'}
    assert result['citations'][0]['type'] == 'event'

async def test_recent_does_not_claim_latest_without_verified_order(app_db, monkeypatch):
    async def classify(request):
        return SimpleNamespace(intent=ai.MeetingEventIntent(disposition='lookup', scope='recent',
            fields=('status',), event_reference=None), trace=ai.JudgeTrace(model='fake', prompt_version='fake', judge_ms=0))
    monkeypatch.setattr(ai, 'classify_meeting_event_facts', classify)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        club = Club(name='최근 행사'); session.add(club); await session.flush()
        session.add(Event(club_id=club.id, title='완료 행사', status=EventStatus.COMPLETE))
        await session.commit(); club_id = club.id
    result, _ = await meeting_event_service.answer(payload(club_id))
    assert '가장 최근인지 확인하지 못했어요' in result['answer']
