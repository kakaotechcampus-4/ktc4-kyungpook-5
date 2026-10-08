"""테스트 공통 fixture."""

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db import session as db_session
from app.main import app

# compose.yml 의 db 서비스가 만드는 테스트 전용 DB.
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://unyounghae:unyounghae@localhost:5432/unyounghae_test"
)
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def client() -> TestClient:
    """서버를 띄우지 않고 앱을 직접 호출한다."""
    return TestClient(app)


@pytest.fixture
def anyio_backend() -> tuple[str, dict]:
    # psycopg 비동기는 Windows 기본 ProactorEventLoop 에서 동작하지 않는다.
    return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}


def _reachable(url: str) -> bool:
    conninfo = make_url(url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    try:
        with psycopg.connect(conninfo, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def db_url() -> str:
    """테스트 DB 주소. 기본 주소에 연결할 수 없으면 DB 테스트를 건너뛴다.

    TEST_DATABASE_URL 을 직접 준 경우(CI)에는 건너뛰지 않고 실패시킨다.
    DB 테스트가 조용히 빠진 채 통과하지 않게 하기 위해서다.
    빈 값도 준 것으로 본다. 등록되지 않은 CI secret 은 빈 문자열로 들어온다.
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit is None:
        if not _reachable(DEFAULT_TEST_DATABASE_URL):
            pytest.skip("테스트 DB에 연결할 수 없어 건너뜁니다 (docker compose up -d db)")
        return DEFAULT_TEST_DATABASE_URL

    url = explicit.strip()
    if not url:
        pytest.fail("TEST_DATABASE_URL 이 비어 있습니다")
    if not _reachable(url):
        pytest.fail("TEST_DATABASE_URL 에 연결할 수 없습니다")
    return url


@pytest.fixture(scope="session")
def alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    # set_main_option 은 % 를 보간 문자로 해석해 비밀번호에 따라 깨질 수 있다.
    cfg.attributes["database_url"] = db_url
    return cfg


@pytest.fixture(scope="session")
def migrated_db_url(db_url: str, alembic_cfg: Config) -> str:
    command.upgrade(alembic_cfg, "head")
    return db_url


@pytest.fixture
def clear_db_caches() -> Iterator[None]:
    """DATABASE_URL 을 바꾸는 테스트 전후로 설정·엔진 캐시를 비운다."""

    def clear() -> None:
        get_settings.cache_clear()
        db_session.get_engine.cache_clear()
        db_session.get_sessionmaker.cache_clear()

    clear()
    yield
    clear()
