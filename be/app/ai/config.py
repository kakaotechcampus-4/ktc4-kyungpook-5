"""AI 전용 설정의 정의 위치

모델 호출: ML API에 HTTP 요청
값이 없어도 import는 성공하고, 실제 호출 시점에 `require_api()`로 확인한다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import AIConfigError


class AISettings(BaseSettings):
    """ML API 호출에 필요한 AI 모듈 설정"""

    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    # ML API 엔드포인트
    api_base_url: str = ""
    # Authorization: Bearer 헤더에 사용할 키
    api_key: str = ""
    # 사용할 모델 식별자
    model: str = ""
    # 단일 요청의 응답 대기 상한(초).
    request_timeout_seconds: float = 60.0

    def require_api(self) -> None:
        """호출 직전에 필수 설정을 확인, 값 노출 X"""
        missing = [
            name
            for name in ("api_base_url", "api_key", "model")
            if not getattr(self, name).strip()
        ]
        if missing:
            names = ", ".join(f"AI_{name.upper()}" for name in missing)
            raise AIConfigError(f"AI 설정이 비어 있습니다: {names}")


@lru_cache(maxsize=1)
def get_settings() -> AISettings:
    """환경변수에서 읽은 설정 재사용"""
    return AISettings()
