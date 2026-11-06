"""Exercise competing plan writes and repeat cancellation against real PostgreSQL."""
import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import EventStatus
from app.db import session as db_session
from app.models.events import Event
from tests.integration.event_seed import add_action, add_event, add_step, owner_with_club

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def test_cancel_repeated_completion_never_advances_or_duplicates(client: TestClient, app_db: None) -> None:
    headers, club = owner_with_club(client, 'cancel-repeat-check')
    event = await add_event(club, status=EventStatus.ON_GOING)
    base = f'/api/v1/events/{event}'
    assert client.post(f'{base}/cancel', headers=headers).status_code == 200
    assert client.post(f'{base}/cancel', headers=headers).status_code == 409
    tasks = client.get(f'{base}/cancel/tasks', headers=headers).json()['data']
    assert len(tasks) == 4
    first = f'{base}/cancel/tasks/{tasks[0]["id"]}/complete'
    assert client.post(first, headers=headers).status_code == 200
    assert client.post(first, headers=headers).status_code == 200  # 이미 끝난 항목은 그대로 돌려준다 (#378)
    current = client.get(f'{base}/cancel/tasks', headers=headers).json()['data']
    assert len(current) == 4 and current[1]['state'] == 'CURRENT'
    for task in tasks[1:]:
        assert client.post(f'{base}/cancel/tasks/{task["id"]}/complete', headers=headers).status_code == 200
    assert client.get(base, headers=headers).json()['data']['status'] == 'CANCELLED'
    assert client.post(f'{base}/cancel/tasks/{tasks[-1]["id"]}/complete', headers=headers).status_code == 200
    assert len(client.get(f'{base}/cancel/tasks', headers=headers).json()['data']) == 4
    assert client.get(base, headers=headers).json()['data']['status'] == 'CANCELLED'


@pytest.mark.parametrize('kind', ['step', 'action'])
async def test_detail_and_removal_race_does_not_lose_successful_edit(client: TestClient, app_db: None, kind: str) -> None:
    headers, club = owner_with_club(client, f'edit-race-{kind}')
    event_id = await add_event(club, status=EventStatus.PLANNING)
    step = await add_step(event_id, 1)
    action = await add_action(event_id, step_id=step)
    detail_path = f'/api/v1/steps/{step}' if kind == 'step' else f'/api/v1/actions/{action}'
    detail_body = {'expectedVersion': 1, 'deadline': '2026-11-08T00:00:00Z'} if kind == 'step' else {'expectedVersion': 1, 'title': '검증 변경'}
    structure_path = f'/api/v1/events/{event_id}/plan/steps'
    async with db_session.get_sessionmaker()() as session:
        await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        detail = asyncio.create_task(asyncio.to_thread(client.patch, detail_path, headers=headers, json=detail_body))
        structure = asyncio.create_task(asyncio.to_thread(client.patch, structure_path, headers=headers,
            json={'expectedRevision': 0, 'codes': ['RESEARCH_VENUE']}))
        await asyncio.sleep(0.2)
        assert not detail.done() and not structure.done()
        await session.commit()
        a, b = await asyncio.wait_for(asyncio.gather(detail, structure), timeout=10)
    if a.status_code == 200:
        assert b.status_code == 409, b.text
        snap = client.get(f'{structure_path}/snapshot', headers=headers).json()['data']
        assert snap['baseRevision'] == 1 and snap['steps'][0]['id'] == step
        if kind == 'step':
            assert snap['steps'][0]['deadline'] == '2026-11-08T00:00:00Z'
        else:
            assert next(item for item in snap['steps'][0]['actions'] if item['id'] == action)['title'] == '검증 변경'
    else:
        assert b.status_code == 200, b.text
        assert a.status_code in (404, 409), a.text
        snap = client.get(f'{structure_path}/snapshot', headers=headers).json()['data']
        assert snap['baseRevision'] == 1 and [s['code'] for s in snap['steps']] == ['RESEARCH_VENUE']


async def test_structure_add_reorder_remove_preserves_retained_rows(client: TestClient, app_db: None) -> None:
    headers, club = owner_with_club(client, 'plan-order-check')
    event = await add_event(club, status=EventStatus.PLANNING)
    url = f'/api/v1/events/{event}/plan/steps'
    first = client.patch(url, headers=headers, json={'expectedRevision': 0, 'codes': ['ASSIGN_ROLES', 'DEMAND_SURVEY']})
    assert first.status_code == 200, first.text
    snapshot = client.get(f'{url}/snapshot', headers=headers).json()['data']
    by_code = {step['code']: step for step in snapshot['steps']}
    action_id = by_code['DEMAND_SURVEY']['actions'][0]['id']
    second = client.patch(url, headers=headers, json={'expectedRevision': 1, 'codes': ['DEMAND_SURVEY', 'ASSIGN_ROLES', 'RESEARCH_VENUE']})
    assert second.status_code == 200, second.text
    snapshot = client.get(f'{url}/snapshot', headers=headers).json()['data']
    assert snapshot['baseRevision'] == 2
    assert [step['code'] for step in snapshot['steps']] == ['DEMAND_SURVEY', 'ASSIGN_ROLES', 'RESEARCH_VENUE']
    assert snapshot['steps'][0]['id'] == by_code['DEMAND_SURVEY']['id']
    assert snapshot['steps'][0]['actions'][0]['id'] == action_id
    third = client.patch(url, headers=headers, json={'expectedRevision': 2, 'codes': ['RESEARCH_VENUE', 'ASSIGN_ROLES']})
    assert third.status_code == 200, third.text
    snapshot = client.get(f'{url}/snapshot', headers=headers).json()['data']
    assert snapshot['baseRevision'] == 3
    assert [step['code'] for step in snapshot['steps']] == ['RESEARCH_VENUE', 'ASSIGN_ROLES']
    assert all(action['id'] != action_id for step in snapshot['steps'] for action in step['actions'])
