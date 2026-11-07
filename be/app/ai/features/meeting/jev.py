"""판단 전용 API Jev로 "이 발화에 기록 조회가 필요한가"의 확률을 받는다 (#255).

Jev는 문장을 만들지 않고, 입력 글과 판단 질문을 받아 질문마다 참일 확률을 돌려준다.
요청 형식이 Laya와 같아서 Laya를 학습하고 잴 때 쓴 입력 글(build_judge_input)과
질문 문구(questions.py)를 그대로 보낸다. 측정(#245)과 같은 요청이다.

    POST {JEV_BASE_URL}/v1/decisions
    {"model": "typesafe/jev-1.14", "state": "<입력 글>", "questions": {"record_lookup": {...}}}
    → {"answers": {"record_lookup": {"noul": 0.83}}, "model": "typesafe/jev-1.14-20261014", ...}

OpenAI SDK에 이 경로가 없어 httpx로 직접 부른다. 실패는 llm.py의 모델 호출과 같은 기준으로
AI 오류 타입으로 바꾼다(docs/errors.md "모델 호출 오류 변환").
"""

import asyncio
import weakref

import httpx

from ...config import get_jev_settings
from ...errors import AIConfigError, AIError, AIInvalidResponseError, AIRetryableError, AITimeoutError
from ...llm import DEFAULT_MAX_RETRIES
from .context import JEV_MODEL
from .questions import RECORD_LOOKUP, judge_questions

# 호출 하나의 대기 상한. 판단 단계 전체의 제한 시간(nodes.JUDGE_TIMEOUT_SECONDS)이 먼저 끊으므로
# 같은 값으로 두어 httpx 기본값(5초)이 먼저 끊지 않게 한다
REQUEST_TIMEOUT_SECONDS = 10.0
# 연결 실패·429·5xx를 다시 보내기 전에 기다리는 시간(초). 두 번째는 두 배를 기다린다
RETRY_BACKOFF_SECONDS = 0.5

# 이벤트 루프마다 연결을 하나 두고 다시 쓴다. 호출마다 새로 연결하면 TLS 연결을 맺는 시간이
# 판단마다 붙는다. 루프가 바뀌면(테스트, 다른 스레드) 그 루프의 연결을 새로 만든다
_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = (
    weakref.WeakKeyDictionary()
)


def _client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
        _clients[loop] = client
    return client


async def call_jev(state: str) -> float:
    """입력 글 하나에 record_lookup이 참일 확률(0~1)을 받는다.

    예: "...[방금] 작년 MT 숙소비 얼마였지?" → 0.83
    임계값과 견주는 일은 부르는 쪽(nodes)이 한다.
    """
    settings = get_jev_settings()
    settings.require()
    body = {"model": JEV_MODEL, "state": state, "questions": judge_questions()}
    headers = {"Authorization": f"Bearer {settings.api_key.get_secret_value()}"}

    for attempt in range(DEFAULT_MAX_RETRIES + 1):
        try:
            response = await _client().post(settings.decisions_url, json=body, headers=headers)
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            converted = _convert(error)
            if converted is None:
                raise
            if not _should_retry(converted) or attempt == DEFAULT_MAX_RETRIES:
                # 원인 예외는 __cause__로만 남긴다. 메시지에는 요청 원문·키를 넣지 않는다
                raise converted from error
            await asyncio.sleep(RETRY_BACKOFF_SECONDS * 2**attempt)
            continue
        return _probability(response)
    raise AssertionError("unreachable")


def _probability(response: httpx.Response) -> float:
    try:
        value = response.json()["answers"][RECORD_LOOKUP]["noul"]
    except (ValueError, KeyError, TypeError) as error:
        raise AIInvalidResponseError("Jev 응답에 조회 확률이 없습니다") from error
    # bool은 int의 하위 타입이라 숫자로 통과하지 않게 먼저 거른다
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise AIInvalidResponseError("Jev 응답의 조회 확률이 0~1 사이의 수가 아닙니다")
    return float(value)


def _convert(error: httpx.TransportError | httpx.HTTPStatusError) -> AIError | None:
    """llm._convert_api_error와 같은 분류. 분류 밖(400 등)이면 None을 돌려 그대로 올린다"""
    if isinstance(error, httpx.TimeoutException):
        return AITimeoutError("Jev 응답이 제한 시간 안에 오지 않았습니다")
    if isinstance(error, httpx.TransportError):
        return AIRetryableError("Jev API에 연결하지 못했습니다")
    status = error.response.status_code
    if status == 429 or status >= 500:
        return AIRetryableError(f"Jev API가 요청을 처리하지 못했습니다 (HTTP {status})")
    if status in (401, 403, 404):
        return AIConfigError(f"Jev API의 주소·키를 확인해야 합니다 (HTTP {status})")
    return None


def _should_retry(error: AIError) -> bool:
    # 시간 초과는 다시 보내도 판단 단계의 제한 시간 안에 끝나기 어렵다
    return isinstance(error, AIRetryableError) and not isinstance(error, AITimeoutError)
