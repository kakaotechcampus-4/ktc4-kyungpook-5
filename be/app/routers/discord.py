"""Discord 연결 엔드포인트. 읽기 전용 — Discord에 글을 쓰는 경로는 없다."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    WRITER_ROLES,
    ensure_member,
    get_current_account,
    require_club_role,
)
from app.core.enums import DiscordConnectionMode
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.discord import DiscordMessage
from app.schemas.common import Envelope
from app.schemas.discord import (
    DiscordConnectionCreateIn,
    DiscordConnectionOut,
    DiscordConnectionPatchIn,
    DiscordMessageOut,
    DiscordSyncOut,
)
from app.services import discord_service

router = APIRouter(prefix="/api/v1", tags=["discord"])


def _message_out(message: DiscordMessage) -> DiscordMessageOut:
    return DiscordMessageOut(
        id=message.id,
        source_id=message.id,
        source_version=message.version,
        channel_id=message.channel_id,
        message_id=message.message_id,
        author_id=message.author_id,
        content=message.content,
        posted_at=message.posted_at,
        created_at=message.created_at,
    )


@router.post(
    "/clubs/{club_id}/discord-connections",
    response_model=Envelope[DiscordConnectionOut],
    status_code=201,
)
async def create_discord_connection(
    club_id: str,
    body: DiscordConnectionCreateIn,
    member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[DiscordConnectionOut]:
    connection = await discord_service.create_connection(
        session,
        club_id=club_id,
        mode=DiscordConnectionMode.LIVE,
        guild_id=body.guild_id,
        channel_ids=body.channel_ids,
        bot_profile=body.bot_profile,
        enabled=body.enabled,
        created_by=member.id,
    )
    return Envelope(data=DiscordConnectionOut.model_validate(connection))


@router.get(
    "/discord-connections/{connection_id}", response_model=Envelope[DiscordConnectionOut]
)
async def get_discord_connection(
    connection_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[DiscordConnectionOut]:
    connection = await discord_service.get_connection(session, connection_id=connection_id)
    await ensure_member(session, club_id=connection.club_id, account=account)
    return Envelope(data=DiscordConnectionOut.model_validate(connection))


@router.patch(
    "/discord-connections/{connection_id}", response_model=Envelope[DiscordConnectionOut]
)
async def update_discord_connection(
    connection_id: str,
    body: DiscordConnectionPatchIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[DiscordConnectionOut]:
    connection = await discord_service.get_connection(session, connection_id=connection_id)
    await ensure_member(
        session, club_id=connection.club_id, account=account, allowed=WRITER_ROLES
    )
    updated = await discord_service.update_connection(
        session,
        connection,
        expected_version=body.expected_version,
        enabled=body.enabled,
        channel_ids=body.channel_ids,
    )
    return Envelope(data=DiscordConnectionOut.model_validate(updated))


@router.post(
    "/discord-connections/{connection_id}/sync",
    response_model=Envelope[DiscordSyncOut],
    status_code=202,
)
async def sync_discord_connection(
    connection_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[DiscordSyncOut]:
    connection = await discord_service.get_connection(session, connection_id=connection_id)
    member = await ensure_member(
        session, club_id=connection.club_id, account=account, allowed=WRITER_ROLES
    )
    job = await discord_service.request_sync(session, connection, requested_by=member.id)
    return Envelope(data=DiscordSyncOut(job_id=job.id))


@router.get(
    "/discord-connections/{connection_id}/messages",
    response_model=Envelope[list[DiscordMessageOut]],
)
async def list_discord_messages(
    connection_id: str,
    limit: int = Query(20, ge=1, le=100),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[DiscordMessageOut]]:
    connection = await discord_service.get_connection(session, connection_id=connection_id)
    await ensure_member(session, club_id=connection.club_id, account=account)
    messages = await discord_service.list_messages(
        session, connection_id=connection_id, limit=limit
    )
    return Envelope(data=[_message_out(message) for message in messages])
