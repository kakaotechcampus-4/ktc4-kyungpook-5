"""공통 LLM 생성과 호출 설정을 관리한다.

채팅 모델과 임베딩 모델을 여기서만 만든다.
구조화 출력 호출과 모델 오류 변환도 여기서 한다. 기능 코드는 AI 오류 타입만 받는다.
"""

import re
from functools import lru_cache
from typing import Any

import openai
from langchain_core.language_models import LanguageModelInput
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, ValidationError

from .config import AISettings, get_settings
from .errors import (
    AIConfigError,
    AIError,
    AIInvalidResponseError,
    AIRetryableError,
    AITimeoutError,
)

# 일시적 오류에만 쓰는 재시도 횟수. 승인·발송 같은 실행은 BE가 담당하므로
# 여기서 재시도해도 같은 행동이 중복 실행되지 않는다.
DEFAULT_MAX_RETRIES = 2

# gpt-5.6-terra 는 /v1/chat/completions 에서 function tools 를 거부한다.
# Agent 가 Tool 을 쓰려면 /v1/responses 를 써야 하므로 호출 경로를 여기에 고정한다.
# 이 경로에서는 추론 깊이를 호출별로 정할 수 있어 기본값을 낮추지 않는다.
# 단순한 Agent·노드는 build_chat_model(reasoning={"effort": "none"}) 처럼 줄여서 쓴다.
USE_RESPONSES_API = True

# text-embedding-3-small 의 기본 출력 차원. 저장소(pgvector) 컬럼 차원이 이 값에
# 묶이므로 상수로 둔다. 모델이나 dimensions 값을 바꾸면 저장된 벡터를 다시 만들어야 한다.
EMBEDDING_DIMENSIONS = 1536

# 게이트웨이는 input 으로 문자열과 문자열 배열만 문서화하고 있다. 기본값(True)은
# tiktoken 으로 토큰 배열을 만들어 보내므로 문자열을 그대로 보내도록 끈다.
# 길이 초과는 자동으로 잘리지 않고 오류로 드러난다. 청킹은 retrieval 에서 한다.
CHECK_EMBEDDING_CTX_LENGTH = False

# 게이트웨이는 허용하지 않은 모델명에 404가 아니라 400과 이 문구로 답한다.
# 예: "Model 'no-such-model' is not allowed. Allowed: [...]"
MODEL_NOT_ALLOWED = re.compile(r"Model '.+' is not allowed")


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


def build_embeddings(
    settings: AISettings | None = None,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    **overrides: Any,
) -> OpenAIEmbeddings:
    """AI 설정으로 임베딩 모델을 만든다.

    채팅 모델과 다른 게이트웨이 주소·키를 쓰므로 설정도 임베딩 항목에서 읽는다.
    출력 차원은 모델 기본값(EMBEDDING_DIMENSIONS)을 쓰고 dimensions 를 보내지 않는다.
    줄여서 저장하려면 저장소 컬럼 차원과 함께 바꾼다.
    """
    settings = settings or get_settings()
    settings.require_embedding()

    params: dict[str, Any] = {
        "model": settings.embedding_model,
        "base_url": settings.embedding_base_url,
        "api_key": settings.resolved_embedding_api_key,
        "timeout": settings.request_timeout_seconds,
        "max_retries": max_retries,
        "check_embedding_ctx_length": CHECK_EMBEDDING_CTX_LENGTH,
    }
    params.update(overrides)

    return OpenAIEmbeddings(**params)


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    """기본 구성의 공용 모델을 재사용한다.

    기능별 조정이 필요하면 캐시를 쓰지 않는 `build_chat_model()`을 호출한다.
    설정을 바꿔 다시 읽어야 하면 `get_settings.cache_clear()`와 함께 비운다.
    """
    return build_chat_model()


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    """기본 구성의 공용 임베딩 모델을 재사용한다.

    색인과 검색이 같은 모델·차원을 써야 하므로 기능별로 따로 만들지 않는다.
    """
    return build_embeddings()


async def ainvoke_structured[T: BaseModel](
    messages: LanguageModelInput,
    schema: type[T],
    *,
    model: ChatOpenAI | None = None,
) -> T:
    """모델을 호출해 `schema`로 검증한 객체를 돌려준다.

    모델 호출 실패는 AI 오류 타입으로 바꿔 올리고, 분류 밖의 예외는 그대로 올린다.
    일시적 오류는 모델의 max_retries만큼 먼저 재시도한 뒤에 변환한다.
    `model`을 주지 않으면 공용 모델을 쓴다. 추론 깊이 등을 바꾸려면
    `build_chat_model()`로 만들어 넘긴다.
    """
    model = model or get_chat_model()
    # include_raw=True면 거절·빈 응답 같은 파싱 실패가 예외 대신 parsing_error로 온다.
    structured = model.with_structured_output(
        schema, method="json_schema", include_raw=True
    )
    try:
        output = await structured.ainvoke(messages)
    except (openai.APIConnectionError, openai.APIStatusError) as error:
        converted = _convert_api_error(error)
        if converted is None:
            raise
        raise converted from error
    except ValidationError as error:
        # SDK가 응답을 schema로 바로 파싱하므로 형식이 다르면 호출 단계에서 실패한다.
        # 다른 모델의 검증 실패는 예상하지 못한 오류라 감싸지 않는다.
        if error.title != schema.__name__:
            raise
        raise _invalid_response(schema) from error

    parsed = output["parsed"]
    if output["parsing_error"] is not None or parsed is None:
        raise _invalid_response(schema) from output["parsing_error"]
    return parsed


def _convert_api_error(
    error: openai.APIConnectionError | openai.APIStatusError,
) -> AIError | None:
    """openai 호출 예외를 AI 오류로 바꾼다. 분류 밖이면 None을 돌려 그대로 올리게 한다.

    원인 예외의 문구는 메시지에 넣지 않는다. 응답 본문에 요청 원문이 섞일 수 있어
    원인은 `__cause__`로만 남긴다.
    """
    # APITimeoutError는 APIConnectionError의 하위 타입이라 먼저 본다.
    if isinstance(error, openai.APITimeoutError):
        return AITimeoutError("모델 응답이 제한 시간 안에 오지 않았습니다")
    if isinstance(error, openai.APIConnectionError):
        return AIRetryableError("모델 API에 연결하지 못했습니다")

    status = error.status_code
    if isinstance(error, openai.RateLimitError) or status >= 500:
        return AIRetryableError(f"모델 API가 요청을 처리하지 못했습니다 (HTTP {status})")
    if isinstance(
        error,
        (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError),
    ) or _is_model_not_allowed(error):
        return AIConfigError(
            f"모델 API의 주소·키·모델명을 확인해야 합니다 (HTTP {status})"
        )
    return None


def _is_model_not_allowed(error: openai.APIStatusError) -> bool:
    """게이트웨이가 모델명 오류를 400으로 돌려준 경우인지 본다.

    본문의 type·code로는 다른 요청 형식 오류와 구분되지 않아 문구로 판별한다.
    문구가 바뀌면 분류 밖의 오류로 그대로 올라가고 check_ml_api.py가 실패로 알린다.
    """
    if not isinstance(error, openai.BadRequestError) or not isinstance(error.body, dict):
        return False
    message = error.body.get("message")
    return isinstance(message, str) and bool(MODEL_NOT_ALLOWED.match(message))


def _invalid_response(schema: type[BaseModel]) -> AIInvalidResponseError:
    return AIInvalidResponseError(f"모델 응답이 {schema.__name__} 형식과 맞지 않습니다")
