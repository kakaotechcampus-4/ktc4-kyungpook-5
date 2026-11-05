"""Terra 고정 외부 웹 검색 adapter.

내부 RAG와 섞지 않고, 현재성·웹 요청 신호가 있는 발화에만 호출한다.
응답의 URL annotation은 회의 카드 출처로 보존한다.
"""

import re
from functools import lru_cache
from html import unescape
from time import monotonic
from typing import Any
from urllib.parse import unquote

import httpx

from ...config import get_web_search_settings
from ...errors import AIConfigError, AIInvalidResponseError, AIRetryableError, AITimeoutError
from .schemas import MeetingUtteranceRequest

WEB_SEARCH_PROMPT_VERSION = "meeting-web-search-v1"
# shortcut: DuckDuckGo HTML 결과를 직접 읽는다. MLAPI는 provider-executed web_search를 막으므로,
# 검색 provider가 필요해지면 공식 검색 API로 교체한다.
def should_search_web(text: str) -> bool:
    """구버전 호환용. 실제 분기는 Jev의 문장 확률을 사용한다."""
    return False


class WebSearchAnswer:
    def __init__(self, answer: str, citations: tuple[dict[str, str], ...], duration_ms: int):
        self.answer = answer
        self.citations = citations
        self.duration_ms = duration_ms


@lru_cache(maxsize=1)
def _settings():
    return get_web_search_settings()


def _responses_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/responses") else f"{base}/responses"


def _output_text(payload: dict[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _citations(payload: dict[str, Any]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            for annotation in (content.get("annotations", []) if isinstance(content, dict) else []):
                if not isinstance(annotation, dict) or annotation.get("type") != "url_citation":
                    continue
                source = annotation.get("url_citation") or annotation
                url = source.get("url") if isinstance(source, dict) else None
                if not isinstance(url, str) or not url or url in seen:
                    continue
                seen.add(url)
                title = source.get("title") if isinstance(source, dict) else None
                rows.append({"type": "web", "url": url, "title": title or url, "text": url})
    return tuple(rows)


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value)).strip()


def _search_results(html: str, limit: int) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    matches = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)',
        html,
        flags=re.S,
    )
    for url, title, tail in matches[:limit]:
        if "uddg=" in url:
            url = unquote(url.split("uddg=", 1)[1].split("&", 1)[0])
        if not url.startswith("http"):
            continue
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</', tail, flags=re.S)
        rows.append({
            "type": "web",
            "url": url,
            "title": _strip_html(title) or url,
            "text": _strip_html(snippet_match.group(1)) if snippet_match else "",
        })
    return tuple(rows)


async def search_web(request: MeetingUtteranceRequest) -> WebSearchAnswer:
    settings = _settings()
    settings.require()
    started = monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.timeout_seconds) as client:
            search_response = await client.get(
                settings.search_engine_url,
                params={"q": request.utterance.text, "kl": "kr-kr"},
                headers={"User-Agent": "unyounghae/1.0"},
            )
            search_response.raise_for_status()
            citations = _search_results(search_response.text, settings.max_results)
            if not citations:
                raise AIInvalidResponseError("외부 검색 결과를 찾지 못했습니다")
            source_text = "\n\n".join(
                f"[{index}] {item['title']}\nURL: {item['url']}\n{item['text']}"
                for index, item in enumerate(citations, 1)
            )
            response = await client.post(
                _responses_url(settings.api_base_url),
                headers={"Authorization": f"Bearer {settings.api_key.get_secret_value()}"},
                json={
                    "model": settings.model,
                    "input": (
                        "한국어로 답하세요. 아래 외부 검색 결과만 사용해 짧고 명확하게 요약하세요. "
                        "각 핵심 사실 끝에 [번호]를 붙이고, 확인할 수 없는 내용은 추정하지 마세요.\n\n"
                        f"질문: {request.utterance.text}\n\n검색 결과:\n{source_text}"
                    ),
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as error:
        raise AITimeoutError("외부 웹 검색이 제한 시간 안에 끝나지 않았습니다") from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 429 or error.response.status_code >= 500:
            raise AIRetryableError("외부 웹 검색 서비스가 요청을 처리하지 못했습니다") from error
        raise AIConfigError("외부 웹 검색 API 주소·키·모델을 확인해야 합니다") from error
    except (httpx.TransportError, ValueError) as error:
        raise AIRetryableError("외부 웹 검색 서비스에 연결하지 못했습니다") from error

    answer = _output_text(payload)
    if not answer or not citations:
        raise AIInvalidResponseError("외부 웹 검색 결과나 출처를 읽지 못했습니다")
    return WebSearchAnswer(answer, citations, round((monotonic() - started) * 1000))
