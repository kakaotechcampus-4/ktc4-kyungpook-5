"""AI 테스트 공통 fixture."""

import pytest

from app.ai.config import AISettings


@pytest.fixture(autouse=True)
def _ignore_env_file(monkeypatch):
    """개발자 PC의 be/.env 값이 테스트 결과에 섞이지 않게 한다.

    AISettings는 실행 위치의 .env를 읽으므로, 테스트는 환경변수와 인자로만 설정을 만든다.
    """
    monkeypatch.setitem(AISettings.model_config, "env_file", None)
