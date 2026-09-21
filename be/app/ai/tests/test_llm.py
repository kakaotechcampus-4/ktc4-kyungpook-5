"""채팅 모델 생성이 AI 설정을 반영하고 키를 노출하지 않는지 검증한다.

모델을 만들기만 하고 ML API를 호출하지 않는다.
"""

import pytest

from app.ai.config import AISettings, get_settings
from app.ai.errors import AIConfigError
from app.ai.llm import DEFAULT_MAX_RETRIES, build_chat_model, get_chat_model

API_BASE_URL = "https://example.test/v1"
API_KEY = "super-secret-key"
MODEL = "gpt-5.6-terra"


@pytest.fixture
def settings(monkeypatch):
    """실행 환경의 AI_ 변수 대신 테스트 값으로 설정을 만든다."""
    for name in ("AI_API_BASE_URL", "AI_API_KEY", "AI_MODEL", "AI_REQUEST_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    return AISettings(api_base_url=API_BASE_URL, api_key=API_KEY, model=MODEL)


def test_설정값이_모델_구성에_반영된다(settings):
    model = build_chat_model(settings)

    assert model.model_name == MODEL
    assert model.openai_api_base == API_BASE_URL
    assert model.request_timeout == settings.request_timeout_seconds
    assert model.max_retries == DEFAULT_MAX_RETRIES


def test_필수_설정이_없으면_모델을_만들지_않는다(settings):
    with pytest.raises(AIConfigError, match="AI_MODEL"):
        build_chat_model(AISettings(api_base_url=API_BASE_URL, api_key=API_KEY))


def test_키를_그대로_노출하지_않는다(settings):
    model = build_chat_model(settings)

    assert API_KEY not in repr(model)
    assert model.openai_api_key.get_secret_value() == API_KEY


def test_temperature는_지정했을_때만_전달한다(settings):
    assert build_chat_model(settings).temperature is None

    other = settings.model_copy(update={"model": "other-model"})
    assert build_chat_model(other, temperature=0.2).temperature == 0.2


def test_gpt_5_계열은_temperature를_적용하지_않는다(settings):
    """모델이 거부하는 값이라 langchain-openai가 요청에서 제거한다."""
    assert build_chat_model(settings, temperature=0.2).temperature is None


def test_chat_completions_경로를_고정한다(settings):
    """모델명이나 요청 내용에 따라 Responses API로 전환되지 않아야 한다."""
    model = build_chat_model(settings)

    assert model.use_responses_api is False
    assert model._use_responses_api({"messages": []}) is False


def test_기능별_구성을_덮어쓸_수_있다(settings):
    model = build_chat_model(settings, max_retries=0, model="other-model")

    assert model.max_retries == 0
    assert model.model_name == "other-model"


def test_공용_모델은_재사용된다(monkeypatch):
    monkeypatch.setenv("AI_API_BASE_URL", API_BASE_URL)
    monkeypatch.setenv("AI_API_KEY", API_KEY)
    monkeypatch.setenv("AI_MODEL", MODEL)
    get_settings.cache_clear()
    get_chat_model.cache_clear()

    try:
        assert get_chat_model() is get_chat_model()
        assert get_chat_model().model_name == MODEL
    finally:
        get_settings.cache_clear()
        get_chat_model.cache_clear()
