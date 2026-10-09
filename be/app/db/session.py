"""DB 엔진과 세션.

엔진은 처음 쓰는 시점에 만든다. DATABASE_URL 이 없는 환경(mock API, DB가 붙기 전의
운영 배포)에서도 앱 import 는 성공해야 한다.

AI 호출 중에는 트랜잭션을 잡지 않는다(#52). 서비스는 get_sessionmaker() 로
조회용 세션을 열고 닫은 뒤 AI 를 호출하고, 저장은 새 세션에서 한다.
"""

from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# 세션을 닫은 뒤에도 조회한 값을 읽을 수 있어야 한다(조회 → 세션 종료 → AI 호출).
SESSION_OPTIONS: dict[str, Any] = {"expire_on_commit": False}


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    # pool_pre_ping: 재배포·DB 재시작 뒤 끊긴 연결을 요청 중에 만나지 않게 한다.
    return create_async_engine(
        get_settings().require_database_url(), pool_pre_ping=True
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), **SESSION_OPTIONS)


async def get_session() -> AsyncIterator[AsyncSession]:
    """라우터용 요청 단위 세션. 커밋은 서비스가 명시적으로 한다."""
    async with get_sessionmaker()() as session:
        yield session
