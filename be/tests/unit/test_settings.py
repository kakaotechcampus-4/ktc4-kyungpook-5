"""DB 없이 도는 BE 설정 테스트."""

from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.db import session as db_session


def test_database_url_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+psycopg://u:p@localhost:5432/d"
    monkeypatch.setenv("DATABASE_URL", url)

    assert Settings().require_database_url() == url


def test_database_url_is_read_from_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # be/.env 에 둔 값을 호스트 실행(uvicorn, alembic)에서 읽어야 한다.
    url = "postgresql+psycopg://u:p@localhost:5432/from_dotenv"
    (tmp_path / ".env").write_text(f"DATABASE_URL={url}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings().require_database_url() == url


def test_blank_database_url_fails_only_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "  ")

    settings = Settings()  # 앱 기동 시점에는 실패하지 않는다

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings.require_database_url()


def _clear_db_caches() -> None:
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()


def test_engine_is_not_created_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    _clear_db_caches()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            db_session.get_engine()
    finally:
        _clear_db_caches()


def test_sessions_keep_loaded_values_after_commit() -> None:
    # 조회 후 세션을 닫고 AI를 호출하는 흐름에서 읽어 둔 값이 만료되면 안 된다.
    assert db_session.SESSION_OPTIONS["expire_on_commit"] is False
