"""BE 실행 환경 설정.

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

    # postgresql+psycopg://user:password@host:5432/dbname
    # 비워두면 앱은 뜨고 DB를 쓰는 시점에 실패한다. mock API와, DB가 붙기 전의
    # 운영 배포가 DB 없이 동작해야 해서 기동 시점에 검사하지 않는다.
    database_url: str = ""

    ai: AISettings = Field(default_factory=AISettings)

    def require_database_url(self) -> str:
        """DB 연결 직전에 주소를 확인한다."""
        if not self.database_url.strip():
            raise RuntimeError("DATABASE_URL 이 비어 있습니다")
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경변수에서 읽은 설정 재사용."""
    return Settings()
