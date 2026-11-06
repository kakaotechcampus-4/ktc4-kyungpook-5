"""요청 키로 계획 대화·생성 결과만 조회하는 API 테스트 (#342).

응답 도중 연결이 끊긴 FE는 결과를 몰라 새 요청을 잠근다. 이 API로 그 요청이
저장됐는지(completed), 아직 처리 중인지(processing), 저장되지 않았는지(not_saved)를
모델을 다시 부르지 않고 확인한다.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import app.ai as ai
from app.core import idempotency
from tests.integration.test_events_planning import (
    _chat,
    _create_event,
    _fake_chat_result,
    _fake_generation_result,
    _leftover_processing_key,
    _owner_with_club,
    app_db,  # noqa: F401  (fixture)
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]


def _lookup(client: TestClient, headers: dict, event_id: str, key: str) -> dict:
    res = client.get(f"/api/v1/events/{event_id}/plan/requests/{key}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def test_저장된_채팅은_AI를_다시_부르지_않고_그때_응답을_돌려준다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    calls = 0

    async def fake_chat(request, *, records=None):
        nonlocal calls
        calls += 1
        return _fake_chat_result(event_type="MT", reply="작년 MT는 가평이었어요.")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat)
    posted = _chat(client, headers, event_id, "lookup-chat")
    assert posted.status_code == 200, posted.text

    found = _lookup(client, headers, event_id, "lookup-chat")

    assert found == {"status": "completed", "result": posted.json()["data"]}
    assert calls == 1


async def test_저장된_버튼_생성도_같은_API로_조회한다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request):
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)
    posted = client.post(
        f"/api/v1/events/{event_id}/plan/generate",
        headers={**headers, "Idempotency-Key": "lookup-button"},
        json={"baseRevision": 0},
    )
    assert posted.status_code == 200, posted.text

    found = _lookup(client, headers, event_id, "lookup-button")

    assert found["status"] == "completed"
    assert found["result"]["generationResult"]["status"] == "generated"


async def test_처리_중이면_processing이고_5분이_지나면_저장되지_않은_것으로_본다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    await _leftover_processing_key(
        client, headers, club_id, event_id, "lookup-fresh", age=timedelta(seconds=10)
    )
    await _leftover_processing_key(
        client, headers, club_id, event_id, "lookup-stale", age=timedelta(minutes=10)
    )

    assert _lookup(client, headers, event_id, "lookup-fresh") == {
        "status": "processing", "result": None,
    }
    # 처리하던 서버가 사라졌다. 저장과 완료 표시가 한 커밋이라 저장되지 않았다.
    assert _lookup(client, headers, event_id, "lookup-stale") == {
        "status": "not_saved", "result": None,
    }


async def test_AI가_실패한_요청과_모르는_키는_저장되지_않음(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def failing_chat(request, *, records=None):
        raise ai.AIRetryableError("일시 오류")

    monkeypatch.setattr("app.ai.chat_planning", failing_chat)
    assert _chat(client, headers, event_id, "lookup-failed").status_code == 503

    assert _lookup(client, headers, event_id, "lookup-failed")["status"] == "not_saved"
    assert _lookup(client, headers, event_id, "never-sent")["status"] == "not_saved"


async def test_다른_행사의_요청은_찾지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_a = _create_event(client, headers, club_id)
    event_b = _create_event(client, headers, club_id)

    async def fake_chat(request, *, records=None):
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat)
    assert _chat(client, headers, event_a, "lookup-a").status_code == 200

    assert _lookup(client, headers, event_a, "lookup-a")["status"] == "completed"
    assert _lookup(client, headers, event_b, "lookup-a")["status"] == "not_saved"


async def test_동아리_밖의_사용자는_조회할_수_없다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    outsider, _other_club = _owner_with_club(client)

    res = client.get(f"/api/v1/events/{event_id}/plan/requests/any", headers=outsider)

    assert res.status_code == 403, res.text


async def test_완료_표시가_실패하면_대화도_저장하지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """턴 저장과 요청 키 완료가 한 커밋이다. 따로 커밋하면 그 사이 서버가 꺼졌을 때
    대화는 저장됐는데 키는 처리 중으로 남아, 조회가 저장된 요청을 처리 중이라고 답한다."""
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_chat(request, *, records=None):
        return _fake_chat_result(event_type="MT")

    async def broken_save_response(*args, **kwargs):
        raise RuntimeError("완료 표시 직전에 서버가 멈춘 상황")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat)
    monkeypatch.setattr(idempotency, "save_response", broken_save_response)
    with pytest.raises(RuntimeError):
        _chat(client, headers, event_id, "lookup-atomic")

    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers).json()["data"]
    messages = client.get(f"/api/v1/events/{event_id}/plan/messages", headers=headers).json()
    assert plan["baseRevision"] == 0
    assert messages["data"] == []
    assert _lookup(client, headers, event_id, "lookup-atomic")["status"] == "not_saved"
