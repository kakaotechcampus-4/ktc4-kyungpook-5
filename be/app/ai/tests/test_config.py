"""AISettings의 환경변수 로딩과 필수값 확인을 검증한다."""

import pytest

from app.ai.config import AISettings
from app.ai.errors import AIConfigError

ENV_NAMES = (
    "AI_API_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_REQUEST_TIMEOUT_SECONDS",
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
