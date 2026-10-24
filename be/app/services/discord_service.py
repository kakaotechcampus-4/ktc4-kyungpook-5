"""Discord 연결 설정, 메시지 수집 반영, 자동 판단.

실제 bot(Gateway·REST) 수집기는 아직 없다. LIVE 연결은 만들 수 있지만 DISCONNECTED로
두고, sync는 실패 작업으로 남긴다. FIXTURE 연결은 TEST_MODE의 이벤트 주입으로
메시지를 받는다. 어느 쪽이든 Discord에 글을 쓰지 않는다.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AgentJobKind,
    DiscordConnectionMode,
    DiscordConnectionStatus,
)
from app.core.exceptions import ApiError, ValidationFailed, VersionConflict
from app.models.agent import AgentJob
from app.models.discord import DiscordConnection, DiscordMessage
from app.schemas.discord import FixtureDiscordEventIn
from app.services import agent_job_service, context_service


class DiscordConnectionNotFound(ApiError):
    status_code = 404
    code = "DISCORD_CONNECTION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 Discord 연결을 찾을 수 없습니다.")


class ConnectionDisabled(ApiError):
    status_code = 409
    code = "CONNECTION_DISABLED"

    def __init__(self) -> None:
        super().__init__("모니터링이 중지된 연결입니다.")


class ChannelNotAllowed(ApiError):
    status_code = 403
    code = "CHANNEL_NOT_ALLOWED"

    def __init__(self) -> None:
        super().__init__("허용하지 않은 채널의 메시지입니다.")


def _status(mode: DiscordConnectionMode, enabled: bool) -> DiscordConnectionStatus:
    if not enabled:
        return DiscordConnectionStatus.PAUSED
    if mode == DiscordConnectionMode.FIXTURE:
        return DiscordConnectionStatus.MONITORING
    # 실제 bot 수집기가 없어 켜 두어도 메시지를 받지 못한다.
    return DiscordConnectionStatus.DISCONNECTED


async def create_connection(
    session: AsyncSession,
    *,
    club_id: str,
    mode: DiscordConnectionMode,
    guild_id: str,
    channel_ids: list[str],
    bot_profile: str | None,
    enabled: bool,
    created_by: str,
) -> DiscordConnection:
    connection = DiscordConnection(
        club_id=club_id,
        mode=mode,
        guild_id=guild_id,
        channel_ids=channel_ids,
        bot_profile=bot_profile,
        enabled=enabled,
        status=_status(mode, enabled),
        created_by=created_by,
    )
    session.add(connection)
    await session.commit()
    await session.refresh(connection)
    return connection


async def get_connection(session: AsyncSession, *, connection_id: str) -> DiscordConnection:
    connection = await session.get(DiscordConnection, connection_id)
    if connection is None:
        raise DiscordConnectionNotFound()
    return connection


async def update_connection(
    session: AsyncSession,
    connection: DiscordConnection,
    *,
    expected_version: int,
    enabled: bool | None,
    channel_ids: list[str] | None,
) -> DiscordConnection:
    if connection.version != expected_version:
        raise VersionConflict()
    if enabled is not None:
        connection.enabled = enabled
    if channel_ids is not None:
        connection.channel_ids = channel_ids
    connection.status = _status(connection.mode, connection.enabled)
    connection.version += 1
    await session.commit()
    await session.refresh(connection)
    return connection


async def request_sync(
    session: AsyncSession, connection: DiscordConnection, *, requested_by: str
) -> AgentJob:
    """읽기 catch-up 작업. 수집기가 없어 지금은 항상 실패로 기록한다."""
    job = await agent_job_service.create_job(
        session,
        club_id=connection.club_id,
        kind=AgentJobKind.DISCORD_SYNC,
        created_by=requested_by,
    )
    agent_job_service.start(session, job, None)
    if connection.mode == DiscordConnectionMode.FIXTURE:
        error = {
            "code": "FIXTURE_CONNECTION",
            "message": "FIXTURE 연결은 외부 Discord에서 읽지 않습니다. 테스트 이벤트를 주입하세요.",
        }
    else:
        error = {
            "code": "DISCORD_COLLECTOR_UNAVAILABLE",
            "message": "실제 Discord 수집기가 아직 연결되지 않았습니다.",
        }
    agent_job_service.fail(session, job, error)
    await session.commit()
    return job


async def list_messages(
    session: AsyncSession, *, connection_id: str, limit: int
) -> list[DiscordMessage]:
    return list(
        await session.scalars(
            select(DiscordMessage)
            .where(DiscordMessage.connection_id == connection_id)
            .order_by(DiscordMessage.posted_at.desc())
            .limit(limit)
        )
    )


async def ingest_fixture_event(
    session: AsyncSession, *, club_id: str, event: FixtureDiscordEventIn
) -> tuple[DiscordMessage, AgentJob | None]:
    """수집기가 받은 이벤트를 반영한다고 보고 메시지를 저장한 뒤 바로 판단한다.

    같은 메시지가 다시 오면(재수집) 새 메시지·판단을 만들지 않는다.
    지금은 MESSAGE_CREATE만 받는다.
    """
    if event.event_type != "MESSAGE_CREATE":
        raise ValidationFailed({"eventType": "지금은 MESSAGE_CREATE만 받습니다."})
    connection = await get_connection(session, connection_id=event.connection_id)
    if connection.club_id != club_id:
        raise DiscordConnectionNotFound()
    if not connection.enabled:
        raise ConnectionDisabled()
    if event.channel_id not in connection.channel_ids:
        raise ChannelNotAllowed()

    existing = await session.scalar(
        select(DiscordMessage).where(
            DiscordMessage.connection_id == connection.id,
            DiscordMessage.message_id == event.message_id,
        )
    )
    if existing is not None:
        return existing, None

    message = DiscordMessage(
        club_id=club_id,
        connection_id=connection.id,
        channel_id=event.channel_id,
        message_id=event.message_id,
        author_id=event.author_id,
        content=event.content,
        posted_at=event.source_occurred_at,
        last_event_id=event.event_id,
    )
    session.add(message)
    await session.flush()
    job, _decision = await context_service.decide_discord_message(session, message=message)
    await session.commit()
    return message, job
