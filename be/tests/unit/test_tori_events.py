import asyncio
from types import SimpleNamespace

from app import ai
from app.core.enums import EventStatus
from app.routers import tori
from app.schemas.tori import ToriMessageIn


def test_tori_event_list_queries_authorized_club_and_reports_status(monkeypatch):
    async def classify(_request):
        return ai.ToriIntentResult(intent='event_list', event_status='PLANNING')

    async def ensure_member(_session, *, club_id, account):
        assert club_id == 'club-1' and account.id == 'account-1'

    async def list_events(_session, *, club_id, status, page, size):
        assert (club_id, status, page, size) == ('club-1', EventStatus.PLANNING, 1, 20)
        return [{'id': 'evt-1', 'title': '준비 행사', 'status': EventStatus.PLANNING, 'start_date': None,
                 'end_date': None, 'dday': None, 'location': None, 'headcount': None,
                 'current_step_name': None, 'step_progress': [], 'pending_approval_count': 0,
                 'payment': None, 'budget': None}], 1

    class Session:
        async def commit(self):
            pass

    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr('app.core.deps.ensure_member', ensure_member)
    monkeypatch.setattr(tori.event_service, 'list_events', list_events)
    result = asyncio.run(tori.message('club-1', ToriMessageIn(message='준비 중인 행사'),
                                      None, SimpleNamespace(id='account-1'), Session()))
    assert result.data.intent == 'event_list'
    assert result.data.reply == '계획 중인 행사 1개예요.'
    assert result.data.card.total == 1
    assert [event.title for event in result.data.card.events] == ['준비 행사']
