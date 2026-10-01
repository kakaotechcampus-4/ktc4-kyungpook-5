"""구조화 출력 호출이 응답을 검증하고 모델 오류를 AI 오류 타입으로 바꾸는지 검증한다.

ML API 대신 가짜 HTTP 응답을 돌려줘 langchain-openai·openai의 실제 처리 경로를 탄다.
"""

import asyncio
import json

import httpx
import openai
import pytest
from pydantic import BaseModel

from app.ai.config import AISettings
from app.ai.errors import (
    AIConfigError,
    AIError,
    AIInvalidResponseError,
    AIRetryableError,
    AITimeoutError,
)
from app.ai.llm import ainvoke_structured, build_chat_model

API_KEY = "super-secret-key"


class Place(BaseModel):
    name: str


class Draft(BaseModel):
    title: str
    headcount: int | None
    places: list[Place]


VALID = {"title": "봄 MT", "headcount": None, "places": [{"name": "가평"}]}


def _response(content: list[dict]) -> dict:
    """Responses API 응답 본문. 검증에 쓰이는 필드만 채운다."""
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "gpt-5.6-terra",
        "output": [
            {
                "type": "message",
                "id": "msg_test",
                "status": "completed",
                "role": "assistant",
                "content": content,
            }
        ],
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
    }


def _text(text: str) -> httpx.Response:
    return httpx.Response(
        200, json=_response([{"type": "output_text", "text": text, "annotations": []}])
    )


def _status(code: int) -> httpx.Response:
    return httpx.Response(code, json={"error": {"message": "gateway error"}})


def _raise(error: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def _call(handler, messages="다음 달에 MT를 가고 싶어"):
    settings = AISettings(
        api_base_url="https://example.test/v1", api_key=API_KEY, model="gpt-5.6-terra"
    )
    # 재시도는 SDK 동작이라 여기서는 끄고 변환만 본다.
    model = build_chat_model(
        settings,
        max_retries=0,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return asyncio.run(ainvoke_structured(messages, Draft, model=model))


def test_응답을_스키마로_검증해_돌려준다():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _text(json.dumps(VALID, ensure_ascii=False))

    result = _call(handler)

    assert result == Draft.model_validate(VALID)
    body = json.loads(requests[0].content)
    assert requests[0].url.path.endswith("/responses")
    assert body["text"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"title": "봄 MT"}),  # 필수 필드 누락
        json.dumps({**VALID, "places": [{"name": 1}]}),  # 중첩 필드 형식 오류
        '{"title": "봄',  # 잘린 JSON
    ],
    ids=["필드_누락", "중첩_형식_오류", "잘린_JSON"],
)
def test_형식이_다른_응답은_AIInvalidResponseError(text):
    with pytest.raises(AIInvalidResponseError) as error:
        _call(lambda request: _text(text))

    assert error.value.__cause__ is not None


def test_거절_응답은_AIInvalidResponseError():
    refusal = httpx.Response(200, json=_response([{"type": "refusal", "refusal": "거절"}]))

    with pytest.raises(AIInvalidResponseError):
        _call(lambda request: refusal)


def test_본문이_없는_응답은_AIInvalidResponseError():
    empty = httpx.Response(200, json={**_response([]), "output": []})

    with pytest.raises(AIInvalidResponseError):
        _call(lambda request: empty)


def test_응답_시간_초과는_AITimeoutError():
    with pytest.raises(AITimeoutError) as error:
        _call(_raise(httpx.ReadTimeout("timeout")))

    assert isinstance(error.value.__cause__, openai.APITimeoutError)


def test_연결_실패는_재시도_가능한_오류():
    with pytest.raises(AIRetryableError) as error:
        _call(_raise(httpx.ConnectError("refused")))

    assert type(error.value) is AIRetryableError


@pytest.mark.parametrize("code", [429, 500, 502, 503])
def test_요청_제한과_서버_오류는_재시도_가능한_오류(code):
    with pytest.raises(AIRetryableError) as error:
        _call(lambda request: _status(code))

    assert type(error.value) is AIRetryableError
    assert isinstance(error.value.__cause__, openai.APIStatusError)


@pytest.mark.parametrize("code", [401, 403, 404])
def test_인증_권한_모델명_오류는_AIConfigError(code):
    with pytest.raises(AIConfigError):
        _call(lambda request: _status(code))


def test_분류_밖의_오류는_감싸지_않는다():
    """요청 형식 오류(400)는 AI 코드 문제라 서버 오류로 드러나야 한다."""
    with pytest.raises(openai.BadRequestError) as error:
        _call(lambda request: _status(400))

    assert not isinstance(error.value, AIError)


def test_오류_메시지에_키와_요청_원문을_남기지_않는다():
    request_text = "회비 통장 비밀번호는 1234"

    def echo(request: httpx.Request) -> httpx.Response:
        # 게이트웨이가 요청 원문을 오류 본문에 담아 돌려주는 경우
        return httpx.Response(
            401, json={"error": {"message": f"{API_KEY} {request_text}"}}
        )

    with pytest.raises(AIConfigError) as error:
        _call(echo, messages=request_text)

    assert API_KEY not in str(error.value)
    assert request_text not in str(error.value)
