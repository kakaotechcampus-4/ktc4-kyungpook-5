from app import ai
from app.core import deps
from app.routers import tori


def test_tori_intro_uses_classifier_and_returns_reply_without_lookup(client, monkeypatch):
    async def classify(request):
        assert request.message == '너의 페르소나는?'
        return ai.ToriIntentResult(intent='self_intro')

    async def ensure_member(_session, *, club_id, account):
        assert club_id == 'club-1'

    class Session:
        async def commit(self):
            pass

    async def starters(_session, club_id):
        assert club_id == 'club-1'
        return ['확인할 일 전부 보여줘']

    monkeypatch.setattr(ai, 'classify_tori_intent', classify)
    monkeypatch.setattr(tori, '_starters', starters)
    monkeypatch.setattr(deps, 'ensure_member', ensure_member)
    monkeypatch.setitem(client.app.dependency_overrides, tori.require_member, object)
    monkeypatch.setitem(client.app.dependency_overrides, tori.get_current_account, object)
    monkeypatch.setitem(client.app.dependency_overrides, tori.get_session, Session)

    response = client.post('/api/v1/clubs/club-1/tori/messages', json={'message': '너의 페르소나는?'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['intent'] == 'self_intro'
    assert '토리예요' in data['reply']
    assert data['records'] is data['tasks'] is data['navigation'] is None
    assert data['suggestions'] == ['확인할 일 전부 보여줘']
