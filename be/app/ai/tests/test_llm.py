"""채팅 모델 생성이 AI 설정을 반영하고 키를 노출하지 않는지 검증한다.

모델을 만들기만 하고 ML API를 호출하지 않는다.
"""

import pytest

from app.ai.config import AISettings, get_settings
from app.ai.errors import AIConfigError
from app.ai.llm import (
    DEFAULT_MAX_RETRIES,
    EMBEDDING_DIMENSIONS,
    build_chat_model,
    build_embeddings,
    get_chat_model,
    get_embeddings,
)

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


def test_responses_api_경로를_고정한다(settings):
    """chat/completions 는 function tools 를 거부하므로 요청 내용과 무관하게 고정한다."""
    model = build_chat_model(settings)

    assert model.use_responses_api is True
    assert model._use_responses_api({"messages": []}) is True


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


EMBEDDING_BASE_URL = "https://mlapi.test/embed/v1"
EMBEDDING_MODEL = "text-embedding-3-small"


@pytest.fixture
def embedding_settings(settings):
    return settings.model_copy(
        update={
            "embedding_base_url": EMBEDDING_BASE_URL,
            "embedding_model": EMBEDDING_MODEL,
        }
    )


def test_임베딩_설정값이_모델_구성에_반영된다(embedding_settings):
    model = build_embeddings(embedding_settings)

    assert model.model == EMBEDDING_MODEL
    assert model.openai_api_base == EMBEDDING_BASE_URL
    assert model.request_timeout == embedding_settings.request_timeout_seconds
    assert model.max_retries == DEFAULT_MAX_RETRIES


def test_임베딩은_채팅과_다른_주소를_쓴다(embedding_settings):
    """게이트웨이가 모델마다 다른 경로로 배포돼 채팅 주소로 보내면 안 된다."""
    assert build_embeddings(embedding_settings).openai_api_base != API_BASE_URL


def test_임베딩_필수_설정이_없으면_모델을_만들지_않는다(settings):
    with pytest.raises(AIConfigError, match="AI_EMBEDDING_BASE_URL"):
        build_embeddings(settings)


def test_임베딩_키를_그대로_노출하지_않는다(embedding_settings):
    model = build_embeddings(embedding_settings)

    assert API_KEY not in repr(model)
    assert model.openai_api_key.get_secret_value() == API_KEY


def test_임베딩은_문자열을_그대로_보낸다(embedding_settings):
    """게이트웨이가 문서화한 input 형식이 문자열과 문자열 배열뿐이다."""
    assert build_embeddings(embedding_settings).check_embedding_ctx_length is False


def test_임베딩_차원은_모델_기본값을_쓴다(embedding_settings):
    """dimensions 를 보내지 않으므로 저장소 컬럼 차원과 어긋나지 않는다."""
    assert build_embeddings(embedding_settings).dimensions is None
    assert EMBEDDING_DIMENSIONS == 1536


def test_임베딩_구성을_덮어쓸_수_있다(embedding_settings):
    model = build_embeddings(embedding_settings, max_retries=0, dimensions=512)

    assert model.max_retries == 0
    assert model.dimensions == 512


def test_공용_임베딩은_재사용된다(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", API_KEY)
    monkeypatch.setenv("AI_EMBEDDING_BASE_URL", EMBEDDING_BASE_URL)
    monkeypatch.setenv("AI_EMBEDDING_MODEL", EMBEDDING_MODEL)
    get_settings.cache_clear()
    get_embeddings.cache_clear()

    try:
        assert get_embeddings() is get_embeddings()
        assert get_embeddings().model == EMBEDDING_MODEL
    finally:
        get_settings.cache_clear()
        get_embeddings.cache_clear()
