"""격리 DB에서 운영 상황, 확인 답변, 복원과 재시도 경계를 검증한다."""
import asyncio
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import ai
from app.core.enums import EventStatus
from app.db import session as db_session
from app.models.events import Event
from app.models.operation_cases import OperationCase
from tests.integration.event_seed import add_event, owner_with_club

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(migrated_db_url, monkeypatch, clear_db_caches) -> AsyncIterator[None]:
    monkeypatch.setenv('DATABASE_URL', migrated_db_url)
    yield
    await db_session.get_engine().dispose()


@pytest.fixture
def fake_ai(monkeypatch):
    requests = []
    async def respond(request):
        requests.append(request)
        if request.answer is None:
            return ai.OperationalSituationResult(status='clarification', question='어떤 장소로 바꿀까요?', options=('강의실', '야외'))
        return ai.OperationalSituationResult(status='suggestion', summary='장소를 확인했어요.', suggestions=('운영진에게 공유하세요.',))
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    return requests


def url(event):
    return f'/api/v1/events/{event}/operation-cases'


async def test_question_answer_result_and_reload(client, app_db, fake_ai):
    headers, club = owner_with_club(client, 'operation')
    event = await add_event(club, expected_headcount=30)
    body = {'clientRequestId': 'case-1', 'situation': '기존 장소가 사용 불가해요'}
    created = client.post(url(event), json=body, headers=headers)
    assert created.status_code == 201, created.text
    case = created.json()['data']; action = case['action']; case_url = f"{url(event)}/{case['id']}"
    assert case['questionStatus'] == 'NEEDS_ANSWER' and action['stepId'] is None
    assert action['content'] == '어떤 장소로 바꿀까요?' and action['allowManual']
    assert fake_ai[0].event_context.expected_headcount == 30
    assert client.post(case_url + '/result', headers=headers).status_code == 409
    assert client.post(url(event), json=body, headers=headers).json()['data']['id'] == case['id']
    assert client.post(url(event), json={**body, 'situation': '다른 상황'}, headers=headers).status_code == 409
    assert len(fake_ai) == 1
    answer = client.post(f"/api/v1/actions/{action['id']}/resolve", headers=headers,
                         json={'expectedVersion': action['version'], 'choice': 'MANUAL', 'manualValue': '도서관'})
    assert answer.status_code == 200, answer.text
    result = client.post(case_url + '/result', headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()['data']['resultStatus'] == 'READY'
    assert fake_ai[-1].answer == '도서관' and fake_ai[-1].clarification_question == action['content']
    restored = client.get(case_url, headers=headers).json()['data']
    assert restored['action']['manualValue'] == '도서관' and restored['result']['suggestions']
    assert client.post(case_url + '/result', headers=headers).status_code == 200 and len(fake_ai) == 2
    assert client.get(url(event), headers=headers).json()['meta']['totalCount'] == 1


async def test_ai_failures_keep_situation_and_answer_and_retry(client, app_db, fake_ai, monkeypatch):
    headers, club = owner_with_club(client, 'operation-fail'); event = await add_event(club)
    calls = 0
    async def flaky(request):
        nonlocal calls
        calls += 1
        if calls in (1, 3): raise ai.AIError('not shown')
        if request.answer is None:
            return ai.OperationalSituationResult(status='clarification', question='어디로 할까요?', options=('실내',))
        return ai.OperationalSituationResult(status='suggestion', summary='실내를 선택했어요.', suggestions=('장소를 확인하세요.',))
    monkeypatch.setattr(ai, 'respond_operational_situation', flaky)
    created = client.post(url(event), headers=headers, json={'clientRequestId': 'retry', 'situation': '장소 문제'})
    assert created.status_code == 201 and created.json()['data']['questionStatus'] == 'FAILED'
    case = created.json()['data']; path = f"{url(event)}/{case['id']}"
    retried = client.post(path+'/question', headers=headers).json()['data']; action = retried['action']
    assert action['options'][0]['label'] == '실내'
    resolved = client.post(f"/api/v1/actions/{action['id']}/resolve", headers=headers,
                           json={'expectedVersion': action['version'], 'choice': action['options'][0]['key']})
    assert resolved.status_code == 200
    failed = client.post(path+'/result', headers=headers).json()['data']
    assert failed['resultStatus'] == 'FAILED' and failed['action']['resolvedChoice'] == action['options'][0]['key']
    assert client.get(path, headers=headers).json()['data']['action']['status'] == 'DONE'
    assert client.post(path+'/result', headers=headers).json()['data']['resultStatus'] == 'READY'


async def test_no_question_and_access_and_status(client, app_db, monkeypatch):
    async def respond(request):
        return ai.OperationalSituationResult(status='suggestion', summary='상황을 확인했어요.', suggestions=('담당자에게 전달하세요.',))
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    headers, club = owner_with_club(client, 'operation-direct'); event = await add_event(club)
    other, other_club = owner_with_club(client, 'operation-other'); other_event = await add_event(other_club)
    body = {'clientRequestId': 'direct', 'situation': '장소는 강의실로 확정됐어요'}
    case = client.post(url(event), headers=headers, json=body).json()['data']
    assert case['questionStatus'] == 'NO_QUESTION' and case['action'] is None and case['resultStatus'] == 'READY'
    assert client.get(f"{url(event)}/{case['id']}", headers=other).status_code == 403
    assert client.get(f"{url(other_event)}/{case['id']}", headers=other).status_code == 404
    planned = await add_event(club, status=EventStatus.PLANNING)
    assert client.post(url(planned), headers=headers, json=body).status_code == 409
    assert client.post(url(event), headers=headers, json={**body, 'situation': ' '}).status_code == 422


async def test_concurrent_request_and_expired_previous_result(client, app_db, monkeypatch):
    headers, club = owner_with_club(client, 'operation-concurrent'); event = await add_event(club)
    started, release = threading.Event(), threading.Event()
    calls = 0
    async def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set(); await asyncio.to_thread(release.wait, 10)
            return ai.OperationalSituationResult(status='clarification', question='이전 질문', options=('옛 값',))
        return ai.OperationalSituationResult(status='suggestion', summary='새 결과', suggestions=('새 제안',))
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    body = {'clientRequestId': 'concurrent', 'situation': '장소 변경 필요'}
    first = asyncio.create_task(asyncio.to_thread(client.post, url(event), headers=headers, json=body))
    assert await asyncio.to_thread(started.wait, 5)
    try:
        duplicate = await asyncio.to_thread(client.post, url(event), headers=headers, json=body)
        case = duplicate.json()['data']; assert case['questionStatus'] == 'PROCESSING'
        path = f"{url(event)}/{case['id']}"
        assert (await asyncio.to_thread(client.post, path+'/question', headers=headers)).status_code == 409
        async with db_session.get_sessionmaker()() as session:
            row = await session.get(OperationCase, case['id']); row.attempt_started_at = datetime.now(UTC)-timedelta(minutes=4)
            await session.commit()
        assert (await asyncio.to_thread(client.get, path, headers=headers)).json()['data']['questionStatus'] == 'FAILED'
        retry = await asyncio.to_thread(client.post, path+'/question', headers=headers)
        assert retry.status_code == 200 and retry.json()['data']['result']['summary'] == '새 결과'
    finally:
        release.set()
    assert (await first).status_code == 201
    restored = (await asyncio.to_thread(client.get, path, headers=headers)).json()['data']
    assert restored['questionStatus'] == 'NO_QUESTION' and restored['action'] is None
    assert restored['result']['summary'] == '새 결과'


async def test_pending_recovery_and_open_question(client, app_db, monkeypatch):
    async def respond(request):
        return ai.OperationalSituationResult(status='clarification', question='어느 실내 공간이 가능한가요?', options=())
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    headers, club = owner_with_club(client, 'operation-pending'); event = await add_event(club)
    async with db_session.get_sessionmaker()() as session:
        case = OperationCase(event_id=event, client_request_id='pending', situation='장소가 필요해요', question_status='PENDING', result_status='NOT_REQUESTED')
        session.add(case); await session.commit(); case_id = case.id
    duplicate = client.post(url(event), headers=headers, json={'clientRequestId':'pending','situation':'장소가 필요해요'})
    assert duplicate.status_code == 201 and duplicate.json()['data']['questionStatus'] == 'PENDING'
    retried = client.post(f'{url(event)}/{case_id}/question', headers=headers)
    assert retried.status_code == 200 and retried.json()['data']['action']['options'] == []
    assert retried.json()['data']['action']['allowManual'] is True


async def test_event_completed_during_result_keeps_answer(client, app_db, monkeypatch):
    started, release = threading.Event(), threading.Event()
    async def respond(request):
        if request.answer is None:
            return ai.OperationalSituationResult(status='clarification', question='어디가 좋나요?', options=('실내',))
        started.set(); await asyncio.to_thread(release.wait, 10)
        return ai.OperationalSituationResult(status='suggestion', summary='실내 선택', suggestions=('확인하세요.',))
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    headers, club = owner_with_club(client, 'operation-complete'); event = await add_event(club)
    case = client.post(url(event), headers=headers, json={'clientRequestId':'close','situation':'장소 변경'}).json()['data']
    action = case['action']; path = f"{url(event)}/{case['id']}"
    assert client.post(f"/api/v1/actions/{action['id']}/resolve", headers=headers,
        json={'expectedVersion':action['version'],'choice':'MANUAL','manualValue':'강당'}).status_code == 200
    pending = asyncio.create_task(asyncio.to_thread(client.post, path+'/result', headers=headers))
    assert await asyncio.to_thread(started.wait, 5)
    try:
        async with db_session.get_sessionmaker()() as session:
            row = await session.get(Event, event); row.status = EventStatus.COMPLETE; await session.commit()
    finally:
        release.set()
    response = await pending
    assert response.status_code == 409
    restored = client.get(path, headers=headers).json()['data']
    assert restored['resultStatus'] == 'FAILED' and restored['action']['manualValue'] == '강당'
    assert restored['error']['code'] == 'EVENT_NOT_ON_GOING'


async def test_migration_preserves_existing_event(client, app_db, alembic_cfg):
    from alembic import command
    headers, club = owner_with_club(client, 'operation-migration')
    event = await add_event(club, title='기존 행사', expected_headcount=24)
    await asyncio.to_thread(command.downgrade, alembic_cfg, '20261103_decision_judge_input')
    try:
        async with db_session.get_sessionmaker()() as session:
            # 뒤에 붙은 migration의 컬럼은 이 시점에 없으므로 ORM 엔터티 대신 필요한 컬럼만 읽는다.
            before = (await session.execute(
                select(Event.title, Event.expected_headcount).where(Event.id == event)
            )).one()
            assert before.title == '기존 행사' and before.expected_headcount == 24
    finally:
        await asyncio.to_thread(command.upgrade, alembic_cfg, 'head')
    async with db_session.get_sessionmaker()() as session:
        after = await session.get(Event, event)
        assert after.title == '기존 행사' and after.expected_headcount == 24
        assert (await session.scalars(select(OperationCase).where(OperationCase.event_id == event))).all() == []


async def test_invalid_event_context_keeps_situation(client, app_db, fake_ai):
    from datetime import date
    headers, club = owner_with_club(client, 'operation-bad-context')
    event = await add_event(club, start_date=date(2026, 12, 3), end_date=date(2026, 12, 2))
    response = client.post(url(event), headers=headers, json={'clientRequestId':'bad-context', 'situation':'장소가 필요해요'})
    assert response.status_code == 201, response.text
    case = response.json()['data']
    assert case['questionStatus'] == 'FAILED' and case['error']['code'] == 'AI_INVALID_INPUT'
    assert case['situation'] == '장소가 필요해요' and not fake_ai


async def test_membership_revoked_during_ai_does_not_create_action(client, app_db, monkeypatch):
    from app.core.enums import MemberRole, MemberStatus
    from app.models.clubs import Member
    from tests.integration.event_seed import member_of
    started, release = threading.Event(), threading.Event()
    async def respond(request):
        started.set(); await asyncio.to_thread(release.wait, 10)
        return ai.OperationalSituationResult(status='clarification', question='어떻게 할까요?', options=('선택',))
    monkeypatch.setattr(ai, 'respond_operational_situation', respond)
    headers, club = owner_with_club(client, 'operation-role'); event = await add_event(club)
    manager = await member_of(client, club, MemberRole.MANAGER)
    pending = asyncio.create_task(asyncio.to_thread(client.post, url(event), headers=headers,
        json={'clientRequestId':'role','situation':'운영 상황'}))
    assert await asyncio.to_thread(started.wait, 5)
    try:
        async with db_session.get_sessionmaker()() as session:
            owner = await session.scalar(select(Member).where(Member.club_id == club, Member.role == MemberRole.OWNER))
            owner.status = MemberStatus.PENDING; await session.commit()
    finally:
        release.set()
    assert (await pending).status_code == 403
    cases = client.get(url(event), headers=manager).json()['data']
    assert len(cases) == 1 and cases[0]['action'] is None


async def test_duplicate_request_rechecks_membership_after_router_check(client, app_db, fake_ai, monkeypatch):
    from app.core.enums import MemberStatus
    from app.models.clubs import Member
    from app.services import action_service
    headers, club = owner_with_club(client, 'operation-duplicate-race')
    event = await add_event(club)
    body = {'clientRequestId': 'same', 'situation': '첫 상황'}
    first = client.post(url(event), headers=headers, json=body)
    assert first.status_code == 201
    original = action_service.lock_operating_event
    revoked = False
    async def lock_and_revoke(session, event_id):
        nonlocal revoked
        locked = await original(session, event_id)
        if not revoked:
            revoked = True
            async with db_session.get_sessionmaker()() as other:
                member = await other.scalar(select(Member).where(Member.club_id == club))
                member.status = MemberStatus.PENDING
                await other.commit()
        return locked
    monkeypatch.setattr(action_service, 'lock_operating_event', lock_and_revoke)
    # Router _event already passed while the member was active; service must recheck.
    assert client.post(url(event), headers=headers, json=body).status_code == 403
