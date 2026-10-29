"""BE 실행 환경 설정.

AI 설정(`AISettings`)은 여기서 새로 선언하지 않고 `app.ai.config`를 그대로 재사용한다.
같은 환경변수를 두 곳에서 각자 읽으면 값이 어긋날 수 있다. `app.ai.config`를 직접
참조하는 것은 설정 로딩 자체가 업무 계약이 아니라 두 모듈이 공유하는 부트스트랩
경계이기 때문이다 (facade/ports/contracts로 나누는 업무 호출 경계와는 별개).
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.config import AISettings


class Settings(BaseSettings):
    # AISettings와 같이 be/에서 실행하는 걸 전제로 .env를 읽는다. 환경변수가 우선한다.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # postgresql+psycopg://user:password@host:5432/dbname
    # 비워두면 앱은 뜨고 DB를 쓰는 시점에 실패한다. mock API와, DB가 붙기 전의
    # 운영 배포가 DB 없이 동작해야 해서 기동 시점에 검사하지 않는다.
    database_url: str = ""

    # 업로드 파일(영수증·CSV 등) 저장 경로. S3 연동 전까지 로컬 디스크를 쓴다.
    # storage_key는 이 경로 기준 상대경로로 남겨 나중에 S3로 바꿔도 호출부가
    # 바뀌지 않게 한다.
    storage_dir: str = "./var/storage"

    # 카카오 로그인(OAuth). 비워두면 /auth/kakao/callback 호출 시 실패한다.
    kakao_rest_api_key: str = ""
    kakao_redirect_uri: str = ""

    # TEST_MODE=true일 때만 /test-support/* 라우트를 등록한다. 운영 환경은 404.
    test_mode: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    stt_url: str = ""
    stt_api_key: SecretStr = SecretStr("")
    stt_model: str = "whisper-large-v3"
    stt_timeout_seconds: float = Field(default=60, gt=0)
    audio_vad_rms_threshold: float = Field(default=450, gt=0)

    web_push_vapid_public_key: str = ""
    web_push_vapid_private_key: SecretStr = SecretStr("")
    web_push_vapid_subject: str = ""
    web_push_timeout_seconds: float = Field(default=10, gt=0)
    web_push_ttl_seconds: int = Field(default=3600, ge=0)
    reminder_dispatcher_enabled: bool = False
    reminder_poll_seconds: float = Field(default=5, gt=0)

    ai: AISettings = Field(default_factory=AISettings)

    def require_database_url(self) -> str:
        """DB 연결 직전에 주소를 확인한다."""
        url = self.database_url.strip()
        if not url:
            raise RuntimeError("DATABASE_URL 이 비어 있습니다")
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """환경변수에서 읽은 설정 재사용."""
    return Settings()
