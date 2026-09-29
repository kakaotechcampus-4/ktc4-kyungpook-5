"""계획 시작·임시 저장 목록 API (이슈 #63).

실제 DB에 저장하고 조회한다. 테스트마다 롤백되어 서로 영향을 주지 않는다.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CLUB_ID = "clb_3a71c0"  # alembic 시드


async def test_db_session_commit_is_rolled_back_after_test_1(
    db_session: AsyncSession,
) -> None:
    db_session.add(Event(club_id=CLUB_ID, title="격리 확인"))
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count()).select_from(Event).where(Event.title == "격리 확인")
    )
    assert count == 1


async def test_db_session_commit_is_rolled_back_after_test_2(
    db_session: AsyncSession,
) -> None:
    count = await db_session.scalar(
        select(func.count()).select_from(Event).where(Event.title == "격리 확인")
    )
    assert count == 0
