"""테스트 공통 fixture."""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_session
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
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    url = explicit or DEFAULT_TEST_DATABASE_URL
    if not _reachable(url):
        if explicit:
            pytest.fail("TEST_DATABASE_URL 에 연결할 수 없습니다")
        pytest.skip("테스트 DB에 연결할 수 없어 건너뜁니다 (docker compose up -d db)")
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
async def db_session(migrated_db_url: str) -> AsyncIterator[AsyncSession]:
    """테스트 하나 동안 쓰는 세션. 끝나면 전부 롤백한다.

    바깥 트랜잭션을 테스트가 잡고, 서비스의 commit()은 savepoint로 처리된다.
    """
    engine = create_async_engine(migrated_db_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """db_session 을 쓰는 앱 클라이언트.

    TestClient 는 앱을 다른 이벤트 루프에서 돌려 이 세션을 함께 쓸 수 없다.
    """

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)
