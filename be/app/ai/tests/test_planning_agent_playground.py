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
    async def process(request, *, search, generate):
        calls.append(request)
        assert search.keywords["club_id"]=="clb_keunnamu"
        assert search.keywords["port"] is playground.memory
        assert generate is playground.run_plan_generation
        return SimpleNamespace(history=(), model_dump=lambda **_: {"reply":"3만 원을 기준으로 잡아둘게요.",
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
    assert response.json()["plan_generation"] is True


def test_button_api_uses_own_entrypoint_and_only_real_history_text(monkeypatch):
    calls=[]
    async def button(request, *, generate):
        calls.append(request)
        assert request.messages[-1].content=="비용을 함께 검토해봐요."
        assert len(request.messages)==2
        assert generate is playground.run_plan_generation
        return SimpleNamespace(model_dump=lambda **_: {"generation":{},"result":{"status":"failed","reason":"재시도"}})
    async def no_agent(*args, **kwargs): raise AssertionError("버튼에서 Agent가 호출됨")
    monkeypatch.setattr(playground,"run_button_plan_generation",button)
    monkeypatch.setattr(playground,"run_planning_agent_turn",no_agent)
    data=payload();data.pop("current_message");data["request_id"]="click-1"
    response=call("POST","/__planning-test/agent/generate",data)
    assert response.status_code==200 and response.json()["source"]=="button"
    assert response.json()["result"]["result"]["status"]=="failed"
    assert calls[0].request_id=="click-1" and calls[0].draft.conditions.fee_per_person==25000


def test_button_api_rejects_orphan_tool_and_fake_chat_payload():
    data=payload();data.pop("current_message");data["request_id"]="click-1"
    data["history"]=[{"type":"tool","content":"missing-call","tool_call_id":"none"}]
    assert call("POST","/__planning-test/agent/generate",data).status_code==422
    assert call("POST","/__planning-test/agent/generate",payload()).status_code==422


def test_button_transport_error_does_not_expose_provider_details(monkeypatch):
    async def fail(*args, **kwargs): raise AIRetryableError("secret-provider-details")
    monkeypatch.setattr(playground,"run_button_plan_generation",fail)
    data=payload();data.pop("current_message");data["request_id"]="click-1"
    response=call("POST","/__planning-test/agent/generate",data)
    assert response.status_code==503 and "secret-provider" not in response.text


# #194: 표시용 사용량은 서버 공통 계산을 따르고 실패 시 중간 이력을 채택하지 않는다.

def test_test_api_reports_server_usage_for_chat_and_button(monkeypatch):
    from langchain_core.messages import AIMessage
    from functools import partial
    from app.ai.features.planning.generation.graph import run_plan_generation
    from app.ai.tests.test_plan_generation_graph import Model
    from app.ai.tests.test_planning_public_workflow import request, scripted
    scripted(monkeypatch,[AIMessage(content='조건은 유지할게요.')])
    payload=dict(draft=request().draft.model_dump(mode='json'),
        history=[dict(type='human' if i%2==0 else 'ai',id=f'prior-{i}',content='이전 상담') for i in range(46)],
        current_message=dict(id='u1',role='user',text='그대로 두자'),reference_date='2026-10-28')
    response=call('POST','/__planning-test/agent/turn',payload)
    assert response.status_code==200
    data=response.json()
    assert data['history_usage']==dict(message_count=48,max_messages=60,near_limit=True)
    monkeypatch.setattr(playground,'run_plan_generation',partial(run_plan_generation,invoke=Model()))
    payload.pop('current_message')
    payload.update(history=data['result']['history'],request_id='click-1')
    generated=call('POST','/__planning-test/agent/generate',payload)
    assert generated.status_code==200
    assert generated.json()['history_usage']==data['history_usage']


def test_test_api_refuses_to_publish_an_over_limit_chat(monkeypatch):
    from langchain_core.messages import AIMessage
    from app.ai.tests.test_planning_public_workflow import request, scripted
    scripted(monkeypatch,[AIMessage(content='조건은 유지할게요.')])
    payload=dict(draft=request().draft.model_dump(mode='json'),
        history=[dict(type='human' if i%2==0 else 'ai',id=f'prior-{i}',content='이전 상담') for i in range(60)],
        current_message=dict(id='u1',role='user',text='그대로 두자'),reference_date='2026-10-28')
    response=call('POST','/__planning-test/agent/turn',payload)
    assert response.status_code==500
    assert 'history_usage' not in response.json()
