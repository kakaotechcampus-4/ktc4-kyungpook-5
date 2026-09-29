"""테스트 공통 fixture."""

import asyncio
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.main import app

# compose.yml 의 db 서비스가 만드는 테스트 전용 DB.
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://unyounghae:unyounghae@localhost:5432/unyounghae_test"
)


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
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    url = explicit or DEFAULT_TEST_DATABASE_URL
    if not _reachable(url):
        if explicit:
            pytest.fail("TEST_DATABASE_URL 에 연결할 수 없습니다")
        pytest.skip("테스트 DB에 연결할 수 없어 건너뜁니다 (docker compose up -d db)")
    return url
