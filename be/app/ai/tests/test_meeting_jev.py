"""Jev 호출(call_jev)이 측정과 같은 요청을 보내고, 실패를 AI 오류 타입으로 바꾸는지 확인한다.

실제 Jev 대신 httpx.MockTransport로 응답을 정해 둔다. 키 없이 돈다.
"""

import asyncio
import json

import httpx
import pytest

from app.ai.config import get_jev_settings
from app.ai.errors import AIConfigError, AIInvalidResponseError, AIRetryableError, AITimeoutError
from app.ai.features.meeting import jev
from app.ai.features.meeting.context import JEV_MODEL
from app.ai.features.meeting.questions import judge_questions

BASE_URL = "https://mlapi.test/jev"
KEY = "test-jev-key"


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("JEV_BASE_URL", BASE_URL)
    monkeypatch.setenv("JEV_API_KEY", KEY)
    monkeypatch.setattr(jev, "RETRY_BACKOFF_SECONDS", 0)
    get_jev_settings.cache_clear()
    yield
    get_jev_settings.cache_clear()


def _answer(noul):
    return httpx.Response(
        200, json={"answers": {"record_lookup": {"noul": noul}}, "model": "typesafe/jev-1.14-20261014"}
    )


def _multi_answer(record, web):
    return httpx.Response(
        200,
        json={
            "answers": {
                "record_lookup": {"noul": record},
                "external_web_search": {"noul": web},
            },
        },
    )


def _call(monkeypatch, handler, state="[방금] 작년 MT 숙소비 얼마였지?"):
    requests = []

    def recording(request):
        requests.append(request)
        return handler(request)

    transport = httpx.MockTransport(recording)
    monkeypatch.setattr(jev, "_client", lambda: httpx.AsyncClient(transport=transport))
    return asyncio.run(jev.call_jev(state)), requests


def test_측정과_같은_요청을_보내고_확률을_돌려준다(monkeypatch):
    probability, [request] = _call(monkeypatch, lambda request: _answer(0.83))

    assert probability == 0.83
    assert str(request.url) == f"{BASE_URL}/v1/decisions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body == {
        "model": JEV_MODEL,
        "state": "[방금] 작년 MT 숙소비 얼마였지?",
        "questions": judge_questions(),
    }


def test_문장_전체_웹_판단을_함께_받는다(monkeypatch):
    decision, _ = _call(monkeypatch, lambda request: _multi_answer(0.1, 0.91))
    # 기존 helper는 기록 확률만 반환하므로 새 구조는 별도 호출로 검증한다.
    assert decision == 0.1

    async def run():
        return await jev.call_jev_decision("대구 공개 행사 일정 알려줘")

    transport = httpx.MockTransport(lambda request: _multi_answer(0.1, 0.91))
    monkeypatch.setattr(jev, "_client", lambda: httpx.AsyncClient(transport=transport))
    result = asyncio.run(run())
    assert (result.record_lookup, result.external_web_search) == (0.1, 0.91)


@pytest.mark.parametrize("status", [401, 403, 404])
def test_주소나_키가_틀리면_설정_오류다(monkeypatch, status):
    with pytest.raises(AIConfigError) as error:
        _call(monkeypatch, lambda request: httpx.Response(status))

    # 다시 해도 같으므로 한 번만 보낸다. 메시지에 키를 남기지 않는다
    assert KEY not in str(error.value)


def test_일시적_오류는_다시_보낸다(monkeypatch):
    responses = iter([httpx.Response(503), httpx.Response(429), _answer(0.1)])

    probability, requests = _call(monkeypatch, lambda request: next(responses))

    assert probability == 0.1
    assert len(requests) == 3


def test_일시적_오류가_계속되면_재시도_오류다(monkeypatch):
    calls = []

    def failing(request):
        calls.append(request)
        return httpx.Response(502)

    with pytest.raises(AIRetryableError, match="HTTP 502"):
        _call(monkeypatch, failing)
    # 처음 한 번 + 다시 두 번
    assert len(calls) == 3


def test_연결하지_못하면_재시도_오류다(monkeypatch):
    def refused(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(AIRetryableError, match="연결"):
        _call(monkeypatch, refused)


def test_응답이_늦으면_시간_초과_오류이고_다시_보내지_않는다(monkeypatch):
    calls = []

    def slow(request):
        calls.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(AITimeoutError):
        _call(monkeypatch, slow)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"answers": {"record_lookup": {"noul": 1.4}}}),
        httpx.Response(200, json={"answers": {"record_lookup": {"noul": True}}}),
    ],
)
def test_확률이_없거나_잘못되면_응답_형식_오류다(monkeypatch, response):
    with pytest.raises(AIInvalidResponseError):
        _call(monkeypatch, lambda request: response)


def test_분류_밖의_오류는_그대로_올린다(monkeypatch):
    # llm.py와 같은 기준이다. 요청 형식 오류(400)는 AI 오류로 감싸지 않는다
    with pytest.raises(httpx.HTTPStatusError):
        _call(monkeypatch, lambda request: httpx.Response(400))


def test_설정이_비어_있으면_부르기_전에_설정_오류다(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "")
    get_jev_settings.cache_clear()

    with pytest.raises(AIConfigError, match="JEV_API_KEY"):
        _call(monkeypatch, lambda request: _answer(0.5))
