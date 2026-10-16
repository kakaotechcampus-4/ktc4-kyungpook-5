"""mini 활동 snapshot과 SSE 이벤트 조회.

캐릭터 표시값(characterState)은 서버가 집계만 하고 그림·동작은 FE가 정한다.
- WORKING: 대기·처리 중인 작업이 있다
- ATTENTION: 처리할 작업은 없고 검토를 기다리는 할 일 후보가 있다
- IDLE: 둘 다 없다. 실패한 작업은 jobs[]에 따로 보여주고 표시값에는 넣지 않는다
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentJobStatus, CharacterState, TaskSuggestionStatus
from app.models.agent import ActivityEvent, AgentJob
from app.models.discord import DiscordConnection
from app.models.tasks import TaskSuggestion

# snapshot에 남겨 보여줄 실패 작업의 기간
FAILED_JOB_WINDOW = timedelta(hours=24)
SNAPSHOT_JOB_LIMIT = 20
_ACTIVE = (AgentJobStatus.QUEUED, AgentJobStatus.RUNNING)


async def latest_cursor(session: AsyncSession, *, club_id: str) -> int:
    return (
        await session.scalar(
            select(func.max(ActivityEvent.id)).where(ActivityEvent.club_id == club_id)
        )
        or 0
    )


async def snapshot(
    session: AsyncSession, *, club_id: str
) -> tuple[int, CharacterState, list[AgentJob], list[DiscordConnection], int]:
    # 이벤트 cursor를 먼저 읽는다. 이후 상태를 읽는 사이 생긴 이벤트는 SSE에서 다시 받는다.
    cursor = await latest_cursor(session, club_id=club_id)
    since = datetime.now(UTC) - FAILED_JOB_WINDOW
    jobs = list(
        await session.scalars(
            select(AgentJob)
            .where(
                AgentJob.club_id == club_id,
                or_(
                    AgentJob.status.in_(_ACTIVE),
                    (AgentJob.status == AgentJobStatus.FAILED)
                    & (AgentJob.modified_at >= since),
                ),
            )
            .order_by(AgentJob.modified_at.desc())
            .limit(SNAPSHOT_JOB_LIMIT)
        )
    )
    connections = list(
        await session.scalars(
            select(DiscordConnection)
            .where(DiscordConnection.club_id == club_id)
            .order_by(DiscordConnection.created_at)
        )
    )
    proposed = (
        await session.scalar(
            select(func.count())
            .select_from(TaskSuggestion)
            .where(
                TaskSuggestion.club_id == club_id,
                TaskSuggestion.status == TaskSuggestionStatus.PROPOSED,
            )
        )
        or 0
    )
    if any(job.status in _ACTIVE for job in jobs):
        state = CharacterState.WORKING
    elif proposed:
        state = CharacterState.ATTENTION
    else:
        state = CharacterState.IDLE
    return cursor, state, jobs, connections, proposed


async def events_after(
    session: AsyncSession, *, club_id: str, cursor: int, limit: int = 100
) -> list[ActivityEvent]:
    return list(
        await session.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.club_id == club_id, ActivityEvent.id > cursor)
            .order_by(ActivityEvent.id)
            .limit(limit)
        )
    )
