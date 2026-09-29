"""DB 없이 도는 BE 설정 테스트."""

import pytest

from app.core.config import Settings


def test_database_url_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+psycopg://u:p@localhost:5432/d"
    monkeypatch.setenv("DATABASE_URL", url)

    assert Settings().require_database_url() == url


def test_blank_database_url_fails_only_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "  ")

    settings = Settings()  # 앱 기동 시점에는 실패하지 않는다

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.require_database_url()
