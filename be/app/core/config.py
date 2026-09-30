"""BE 실행 환경 설정.

DATABASE_URL 등 BE 자체 설정은 DB 연결 작업(이슈 #63)에서 이 파일에 추가한다.

AI 설정(`AISettings`)은 여기서 새로 선언하지 않고 `app.ai.config`를 그대로 재사용한다.
같은 환경변수를 두 곳에서 각자 읽으면 값이 어긋날 수 있다. `app.ai.config`를 직접
참조하는 것은 설정 로딩 자체가 업무 계약이 아니라 두 모듈이 공유하는 부트스트랩
경계이기 때문이다 (facade/ports/contracts로 나누는 업무 호출 경계와는 별개).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.config import AISettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    ai: AISettings = Field(default_factory=AISettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경변수에서 읽은 설정 재사용."""
    return Settings()
