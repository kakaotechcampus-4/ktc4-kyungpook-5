"""AI 전용 설정의 정의 위치

모델 호출: ML API에 HTTP 요청
값이 없어도 import는 성공하고, 실제 호출 시점에 `require_api()`로 확인한다.
임베딩은 게이트웨이의 별도 엔드포인트라 주소·모델을 따로 받고 `require_embedding()`으로 확인한다.
"""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import AIConfigError


# 빈 값으로 둔 환경변수를 미설정과 같게 보기 위해 기본값을 한 곳에 둔다.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0


def _text(value: str | SecretStr) -> str:
    """설정값의 원문. SecretStr도 같은 방식으로 비어 있는지 본다."""
    return value.get_secret_value() if isinstance(value, SecretStr) else value


class AISettings(BaseSettings):
    """ML API 호출에 필요한 AI 모듈 설정"""

    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    # ML API 엔드포인트
    api_base_url: str = ""
    # Authorization: Bearer 헤더에 사용할 키.
    # SecretStr이라 repr·model_dump 등 설정을 문자열로 만드는 경로에 값이 남지 않는다.
    # 실제 값이 필요하면 api_key.get_secret_value()로 꺼낸다.
    api_key: SecretStr = SecretStr("")
    # 사용할 모델 식별자
    model: str = ""
    # 단일 요청의 응답 대기 상한(초). 채팅·임베딩 호출에 함께 적용한다.
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS

    # --- 임베딩 -------------------------------------------------------
    # 임베딩은 채팅 모델과 다른 게이트웨이 주소로 배포된다(.../v1/embeddings).
    # api_base_url을 재사용하면 채팅 배포로 요청이 가므로 주소를 따로 받는다.
    embedding_base_url: str = ""
    # 임베딩 배포의 키가 채팅과 다를 수 있어 따로 둔다.
    # 비워두면 같은 계정의 키로 보고 api_key를 쓴다.
    embedding_api_key: SecretStr = SecretStr("")
    # 게이트웨이가 지원하는 임베딩 모델 식별자.
    embedding_model: str = ""

    @property
    def resolved_embedding_api_key(self) -> SecretStr:
        """임베딩 호출에 쓸 키. 따로 주지 않았으면 채팅과 같은 키를 쓴다."""
        if _text(self.embedding_api_key).strip():
            return self.embedding_api_key
        return self.api_key

    @field_validator("request_timeout_seconds", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """`AI_REQUEST_TIMEOUT_SECONDS=` 처럼 빈 값으로 둔 경우 기본값을 쓴다.

        .env 에 항목만 남기고 값을 비워두는 경우가 흔한데,
        환경변수는 빈 문자열로 전달되므로 미설정과 달리 숫자 변환에 실패한다.
        """
        if isinstance(value, str) and not value.strip():
            return DEFAULT_REQUEST_TIMEOUT_SECONDS
        return value

    def _require(self, *names: str) -> None:
        """비어 있는 항목을 환경변수 이름으로 알린다. 값은 노출하지 않는다."""
        missing = [name for name in names if not _text(getattr(self, name)).strip()]
        if missing:
            shown = ", ".join(f"AI_{name.upper()}" for name in missing)
            raise AIConfigError(f"AI 설정이 비어 있습니다: {shown}")

    def require_api(self) -> None:
        """채팅 모델 호출 직전에 필수 설정을 확인한다."""
        self._require("api_base_url", "api_key", "model")

    def require_embedding(self) -> None:
        """임베딩 호출 직전에 필수 설정을 확인한다.

        키는 채팅과 같은 것을 쓸 수 있어 resolved_embedding_api_key로 본다.
        """
        self._require("embedding_base_url", "embedding_model")
        if not _text(self.resolved_embedding_api_key).strip():
            raise AIConfigError(
                "AI 설정이 비어 있습니다: AI_EMBEDDING_API_KEY 또는 AI_API_KEY"
            )


@lru_cache(maxsize=1)
def get_settings() -> AISettings:
    """환경변수에서 읽은 설정 재사용"""
    return AISettings()
