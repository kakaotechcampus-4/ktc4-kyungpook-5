import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.ai.config import WebSearchSettings, get_web_search_settings
from app.ai.errors import AIInvalidResponseError
from app.ai.features.meeting.schemas import JudgeUtteranceRequest, MeetingUtterance
from app.ai.features.meeting import web_search


def request(text: str) -> JudgeUtteranceRequest:
    now = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
    return JudgeUtteranceRequest(
        meeting_id="mtg_test",
        club_id="clb_test",
        utterance=MeetingUtterance(
            utterance_id="utt_test", seq=1, text=text, started_at=now, ended_at=now
        ),
    )


def test_web_hint_helper_is_disabled_and_does_not_decide_from_keywords():
    assert not web_search.should_search_web("현재 대구 날씨 알려줘")
    assert not web_search.should_search_web("점심 뭐 먹지")


def test_web_search_requires_enabled_config(monkeypatch):
    monkeypatch.setattr(web_search, "_settings", lambda: WebSearchSettings())
    with pytest.raises(Exception, match="비활성화"):
        asyncio.run(web_search.search_web(request("현재 날씨")))


def test_web_search_parses_citations(monkeypatch):
    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "output_text": "오늘은 맑습니다.",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "오늘은 맑습니다.",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url_citation": {"url": "https://example.com/weather", "title": "날씨"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            request=httpx.Request("POST", "https://example.test/v1/responses"),
        )

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return await handler(None)

        async def get(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                text='<a class="result__a" href="https://example.com/weather">날씨</a><a class="result__snippet">맑음</a>',
                request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
            )

    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **_kwargs: MockClient())
    monkeypatch.setattr(
        web_search,
        "_settings",
        lambda: WebSearchSettings(
            enabled=True, api_base_url="https://example.test/v1", api_key="test"
        ),
    )
    result = asyncio.run(web_search.search_web(request("현재 날씨")))
    assert result.answer == "오늘은 맑습니다."
    assert result.citations[0]["url"] == "https://example.com/weather"


def test_web_search_rejects_empty_answer(monkeypatch):
    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                json={"output_text": ""},
                request=httpx.Request("POST", "https://example.test/v1/responses"),
            )

        async def get(self, *_args, **_kwargs):
            return httpx.Response(
                200,
                text='<a class="result__a" href="https://example.com/weather">날씨</a><a class="result__snippet">맑음</a>',
                request=httpx.Request("GET", "https://html.duckduckgo.com/html/"),
            )

    monkeypatch.setattr(web_search.httpx, "AsyncClient", lambda **_kwargs: MockClient())
    monkeypatch.setattr(
        web_search,
        "_settings",
        lambda: WebSearchSettings(
            enabled=True, api_base_url="https://example.test/v1", api_key="test"
        ),
    )
    with pytest.raises(AIInvalidResponseError):
        asyncio.run(web_search.search_web(request("현재 날씨")))
