"""Tool 모델 호출의 설정·오류 경계. 실제 네트워크를 사용하지 않는다."""

import asyncio

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.ai.errors import AIInvalidResponseError, AITimeoutError
from app.ai.llm import ainvoke_with_tools


class StubModel:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def bind_tools(self, tools, **kwargs):
        self.kwargs = kwargs
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.parametrize("allow_tools,choice", [(True,"auto"),(False,"none")])
def test_binding_controls_tool_choice_and_disables_parallel_calls_by_default(allow_tools, choice):
    model = StubModel(AIMessage(content="안녕하세요"))
    result = asyncio.run(ainvoke_with_tools([], tools=[{"type":"function"}], allow_tools=allow_tools, model=model))
    assert result.text == "안녕하세요"
    assert model.kwargs == {"parallel_tool_calls":False,"tool_choice":choice}


@pytest.mark.parametrize("enabled", [False, True])
def test_planning_agent_passes_its_parallel_setting(monkeypatch, enabled):
    # 행사계획 Agent는 PARALLEL_TOOL_CALLS 한 곳의 값을 보낸다. 지금은 True다(#274에서 채택).
    from app.ai.features.planning.agent import nodes
    assert nodes.PARALLEL_TOOL_CALLS is True
    model = StubModel(AIMessage(content="안녕하세요"))
    monkeypatch.setattr(nodes, "PARALLEL_TOOL_CALLS", enabled)
    monkeypatch.setattr(nodes, "ainvoke_with_tools",
                        lambda messages, **kwargs: ainvoke_with_tools(messages, model=model, **kwargs))
    asyncio.run(nodes.call_agent_model([], allow_tools=True))
    assert model.kwargs == {"parallel_tool_calls":enabled,"tool_choice":"auto"}


def test_api_timeout_uses_common_error_without_raw_details():
    model = StubModel(openai.APITimeoutError(request=httpx.Request("POST","https://example.test")))
    with pytest.raises(AITimeoutError):
        asyncio.run(ainvoke_with_tools([],tools=[],model=model))


@pytest.mark.parametrize("response", [HumanMessage(content="wrong role"), AIMessage(content="",invalid_tool_calls=[
    {"name":"broken","args":"not json","id":"bad","error":"parse"}])])
def test_invalid_message_or_unparseable_tool_is_rejected(response):
    with pytest.raises(AIInvalidResponseError):
        asyncio.run(ainvoke_with_tools([],tools=[],model=StubModel(response)))


def test_tool_requested_after_disable_is_rejected():
    response=AIMessage(content="",tool_calls=[{"id":"c1","name":"change","args":{}}])
    with pytest.raises(AIInvalidResponseError):
        asyncio.run(ainvoke_with_tools([],tools=[],allow_tools=False,model=StubModel(response)))
