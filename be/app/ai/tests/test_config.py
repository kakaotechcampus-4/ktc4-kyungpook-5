"""AISettings의 환경변수 로딩과 필수값 확인을 검증한다."""

import pytest

from app.ai.config import AISettings
from app.ai.errors import AIConfigError

ENV_NAMES = (
    "AI_API_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_REQUEST_TIMEOUT_SECONDS",
    "AI_EMBEDDING_BASE_URL",
    "AI_EMBEDDING_API_KEY",
    "AI_EMBEDDING_MODEL",
)


@pytest.fixture
def clean_env(monkeypatch):
    """실행 환경의 AI_ 변수가 결과에 섞이지 않게 한다."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_설정이_비어도_생성된다(clean_env):
    settings = AISettings()

    assert settings.api_base_url == ""
    assert settings.request_timeout_seconds == 60.0


def test_필수값이_없으면_확인_시점에_실패한다(clean_env):
    with pytest.raises(AIConfigError) as error:
        AISettings().require_api()

    message = str(error.value)
    assert "AI_API_BASE_URL" in message
    assert "AI_API_KEY" in message
    assert "AI_MODEL" in message


def test_공백만_있는_값은_비어_있는_것으로_본다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_API_BASE_URL", "   ")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gpt-5.6-terra")

    with pytest.raises(AIConfigError, match="AI_API_BASE_URL"):
        AISettings().require_api()


def test_오류_메시지에_키_값을_남기지_않는다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "super-secret-key")

    with pytest.raises(AIConfigError) as error:
        AISettings().require_api()

    assert "super-secret-key" not in str(error.value)


def test_환경변수를_읽는다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_API_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "gpt-5.6-terra")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "10")

    settings = AISettings()
    settings.require_api()

    assert settings.api_base_url == "https://example.test/v1"
    assert settings.model == "gpt-5.6-terra"
    assert settings.request_timeout_seconds == 10.0


def test_설정을_문자열로_만들어도_키가_남지_않는다(clean_env, monkeypatch):
    """예외 출력·로그처럼 설정 객체를 통째로 찍는 경로를 막는다."""
    monkeypatch.setenv("AI_API_KEY", "super-secret-key")

    settings = AISettings()

    assert "super-secret-key" not in repr(settings)
    assert "super-secret-key" not in str(settings)
    assert "super-secret-key" not in settings.model_dump_json()
    assert settings.api_key.get_secret_value() == "super-secret-key"


def test_요청_시간_제한을_빈_값으로_두면_기본값을_쓴다(clean_env, monkeypatch):
    """.env 에 항목만 남기고 값을 비워두는 경우를 미설정과 같게 본다."""
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "")

    assert AISettings().request_timeout_seconds == 60.0

    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "   ")
    assert AISettings().request_timeout_seconds == 60.0


def test_임베딩_설정이_없으면_확인_시점에_실패한다(clean_env):
    with pytest.raises(AIConfigError) as error:
        AISettings(api_key="test-key").require_embedding()

    message = str(error.value)
    assert "AI_EMBEDDING_BASE_URL" in message
    assert "AI_EMBEDDING_MODEL" in message


def test_임베딩_키를_비워두면_채팅_키를_쓴다(clean_env, monkeypatch):
    """게이트웨이 배포가 달라도 같은 계정의 키를 쓰는 경우를 받는다."""
    monkeypatch.setenv("AI_API_KEY", "shared-key")
    monkeypatch.setenv("AI_EMBEDDING_BASE_URL", "https://mlapi.test/embed/v1")
    monkeypatch.setenv("AI_EMBEDDING_MODEL", "text-embedding-3-small")

    settings = AISettings()
    settings.require_embedding()

    assert settings.resolved_embedding_api_key.get_secret_value() == "shared-key"


def test_임베딩_키를_따로_주면_그것을_쓴다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "chat-key")
    monkeypatch.setenv("AI_EMBEDDING_API_KEY", "embedding-key")

    assert AISettings().resolved_embedding_api_key.get_secret_value() == "embedding-key"


def test_키가_둘_다_없으면_임베딩_확인이_실패한다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_EMBEDDING_BASE_URL", "https://mlapi.test/embed/v1")
    monkeypatch.setenv("AI_EMBEDDING_MODEL", "text-embedding-3-small")

    with pytest.raises(AIConfigError, match="AI_EMBEDDING_API_KEY"):
        AISettings().require_embedding()


def test_임베딩_설정을_문자열로_만들어도_키가_남지_않는다(clean_env, monkeypatch):
    monkeypatch.setenv("AI_EMBEDDING_API_KEY", "super-secret-embedding-key")

    settings = AISettings()

    assert "super-secret-embedding-key" not in repr(settings)
    assert "super-secret-embedding-key" not in settings.model_dump_json()
