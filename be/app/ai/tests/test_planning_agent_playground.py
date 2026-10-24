"""새 테스트 UI API: 초안·이력을 전달하고 세션 저장 없이 응답한다."""

from types import SimpleNamespace

from app.ai.errors import AIRetryableError
from app.ai.tests.test_planning_playground import call
from app.ai.scripts import planning_playground as playground


def payload():
    return {"draft": {"conditions": {"fee_per_person":25000}},
            "current_message": {"id":"u2","role":"user","text":"일단 그렇게 잡자"},
            "history":[{"type":"human","content":"참가비 3만 원이면 어때?","id":"u1"},
                       {"type":"ai","content":"비용을 함께 검토해봐요."}],
            "reference_date":"2026-10-24","timezone":"Asia/Seoul"}


def test_agent_api_forwards_draft_and_history_without_legacy_call(monkeypatch):
    calls=[]
    async def process(request, *, search):
        calls.append(request)
        assert search.keywords["club_id"]=="clb_keunnamu"
        assert search.keywords["port"] is playground.memory
        return SimpleNamespace(model_dump=lambda **_: {"reply":"3만 원을 기준으로 잡아둘게요.",
            "draft":{"conditions":{"fee_per_person":30000}},"history":[]})
    async def legacy(*args, **kwargs):
        raise AssertionError("legacy was called")
    monkeypatch.setattr(playground,"run_planning_agent_turn",process)
    monkeypatch.setattr(playground,"process_planning_turn",legacy)
    data=payload()
    response=call("POST","/__planning-test/agent/turn",data)
    assert response.status_code==200
    assert response.json()["result"]["draft"]["conditions"]["fee_per_person"]==30000
    assert calls[0].draft.conditions.fee_per_person==25000
    assert calls[0].history[0].content=="참가비 3만 원이면 어때?"
    assert data==payload() and "elapsed_ms" in response.json()


def test_agent_failure_is_safe_and_retryable(monkeypatch):
    async def fail(*args, **kwargs):
        raise AIRetryableError("secret-provider-details")
    monkeypatch.setattr(playground,"run_planning_agent_turn",fail)
    response=call("POST","/__planning-test/agent/turn",payload())
    assert response.status_code==503
    assert "secret-provider" not in response.text
    assert "현재 조건은 유지" in response.text


def test_agent_rejects_incomplete_tool_history_before_execution():
    data=payload()
    data["history"]=[{"type":"tool","content":"missing-call","tool_call_id":"none"}]
    assert call("POST","/__planning-test/agent/turn",data).status_code==422


def test_health_reports_new_agent_version():
    response=call("GET","/__planning-test/health")
    assert response.status_code==200
    assert response.json()["agent_version"]==playground.PROMPT_VERSION
    assert response.json()["record_search"] is True
