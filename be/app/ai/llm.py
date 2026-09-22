"""공통 LLM 생성과 호출 설정을 관리한다.

"""

from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI

from .config import AISettings, get_settings

# 일시적 오류에만 쓰는 재시도 횟수. 승인·발송 같은 실행은 BE가 담당하므로
# 여기서 재시도해도 같은 행동이 중복 실행되지 않는다.
DEFAULT_MAX_RETRIES = 2

# gpt-5.6-terra 는 /v1/chat/completions 에서 function tools 를 거부한다.
# Agent 가 Tool 을 쓰려면 /v1/responses 를 써야 하므로 호출 경로를 여기에 고정한다.
# 이 경로에서는 추론 깊이를 호출별로 정할 수 있어 기본값을 낮추지 않는다.
# 단순한 Agent·노드는 build_chat_model(reasoning={"effort": "none"}) 처럼 줄여서 쓴다.
USE_RESPONSES_API = True


def build_chat_model(
    settings: AISettings | None = None,
    *,
    temperature: float | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    **overrides: Any,
) -> ChatOpenAI:
    """AI 설정으로 채팅 모델을 만든다 - LLM 객체를 만드는 함수
    
    기능별로 다른 구성이 필요하면 `overrides`로 덮어쓴다.
    답변을 일정하게 유지해야 하면 온도 대신 프롬프트와 구조화 출력으로 다룬다.
    """
    settings = settings or get_settings()
    settings.require_api()

    params: dict[str, Any] = {
        "model": settings.model,
        "base_url": settings.api_base_url,
        # config에서 이미 SecretStr이라 로그·예외 문자열에 값이 그대로 남지 않는다.
        "api_key": settings.api_key,
        "timeout": settings.request_timeout_seconds,
        "max_retries": max_retries,
        "use_responses_api": USE_RESPONSES_API,
    }
    if temperature is not None:
        params["temperature"] = temperature
    params.update(overrides)

    return ChatOpenAI(**params)


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    """기본 구성의 공용 모델을 재사용한다.

    기능별 조정이 필요하면 캐시를 쓰지 않는 `build_chat_model()`을 호출한다.
    설정을 바꿔 다시 읽어야 하면 `get_settings.cache_clear()`와 함께 비운다.
    """
    return build_chat_model()
