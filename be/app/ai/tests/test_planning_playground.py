"""로컬 테스트 API의 상태 전달과 오류 비노출을 확인한다. 실제 API는 호출하지 않는다."""

import asyncio
from types import SimpleNamespace

import httpx

from app.ai.scripts import planning_playground as playground


def payload():
    return {"club_id": "clb_keunnamu", "question_state": {"event_id": "e1"},
            "extraction_input": {"event_id": "e1", "request_id": "r1", "base_version": 0,
                "conditions": {"headcount": 40}, "current_message": {"id": "m1", "role": "user", "text": "MT"},
                "reference_date": "2026-10-23", "timezone": "Asia/Seoul"}}


def call(method, path, body=None):
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=playground.app), base_url="http://test") as client:
            return await client.request(method, path, json=body)
    return asyncio.run(request())


def test_turn_forwards_browser_state_without_saving(monkeypatch):
    calls = []
    async def process(request, *, port):
        calls.append(request)
        return SimpleNamespace(model_dump=lambda **_: {"reply": "응답", "collected": {"headcount": 40}})
    monkeypatch.setattr(playground, "process_planning_turn", process)
    data = payload()
    response = call("POST", "/__planning-test/turn", data)
    assert response.status_code == 200 and response.json()["result"]["reply"] == "응답"
    assert calls[0].extraction_input.conditions.headcount == 40
    assert "elapsed_ms" in response.json() and data == payload()


def test_errors_do_not_expose_provider_details(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("secret-token-and-internal-address")
    monkeypatch.setattr(playground, "process_planning_turn", fail)
    response = call("POST", "/__planning-test/turn", payload())
    assert response.status_code == 500
    assert "secret-token" not in response.text and "현재 조건은 유지" in response.text


def test_rejects_non_fixture_club_before_model_call():
    data = payload(); data["club_id"] = "another"
    assert call("POST", "/__planning-test/turn", data).status_code == 400


def test_record_index_failure_keeps_original_memory(monkeypatch):
    original = playground.memory
    async def fail(*args, **kwargs):
        raise RuntimeError("sensitive")
    monkeypatch.setattr(playground, "fixture_count", 0)
    monkeypatch.setattr(playground, "index_record_chunks", fail)
    response = call("POST", "/__planning-test/records", {})
    assert response.status_code == 500 and "sensitive" not in response.text
    assert playground.memory is original and playground.fixture_count == 0
