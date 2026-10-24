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
def test_binding_controls_tool_choice_and_disables_parallel_calls(allow_tools, choice):
    model = StubModel(AIMessage(content="안녕하세요"))
    result = asyncio.run(ainvoke_with_tools([], tools=[{"type":"function"}], allow_tools=allow_tools, model=model))
    assert result.text == "안녕하세요"
    assert model.kwargs == {"parallel_tool_calls":False,"tool_choice":choice}


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
