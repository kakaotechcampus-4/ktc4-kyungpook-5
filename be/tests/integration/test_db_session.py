"""요청 단위 세션이 실제 DB에 연결되는지 확인한다."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import session as db_session

pytestmark = [pytest.mark.db, pytest.mark.anyio]


def _clear_db_caches() -> None:
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()


@pytest.fixture
async def app_db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", db_url)
    _clear_db_caches()
    yield
    # 캐시된 엔진의 연결은 이 테스트의 이벤트 루프에 묶여 있어 여기서 닫는다.
    await db_session.get_engine().dispose()
    _clear_db_caches()


async def test_get_session_yields_connected_session(app_db: None) -> None:
    sessions = db_session.get_session()
    session = await anext(sessions)
    try:
        assert isinstance(session, AsyncSession)
        assert (await session.execute(text("select 1"))).scalar_one() == 1
    finally:
        await sessions.aclose()
