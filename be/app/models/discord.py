"""Discord 채널 연결과 수집한 메시지.

읽기 전용이다. 게시·DM·멘션 전송은 하지 않는다. Discord ID(snowflake)는
JS 숫자로 다루면 정밀도가 깨져 문자열로 저장한다.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DiscordConnectionMode, DiscordConnectionStatus
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk

DISCORD_ID_LENGTH = 32


class DiscordConnection(IdMixin, TimestampMixin, Base):
    """동아리 하나가 읽는 Discord 서버와 허용 채널.

    bot token은 저장하지 않는다. bot_profile은 서버 환경에 등록한 bot 설정의 이름이다.
    """

    __tablename__ = "discord_connections"
    __id_prefix__ = "dsc"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    mode: Mapped[DiscordConnectionMode] = mapped_column(
        enum_column(DiscordConnectionMode), nullable=False
    )
    guild_id: Mapped[str] = mapped_column(String(DISCORD_ID_LENGTH), nullable=False)
    # 허용 채널 Discord ID 목록. 이 밖의 채널 메시지는 저장·분석하지 않는다.
    channel_ids: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    bot_profile: Mapped[str | None] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[DiscordConnectionStatus] = mapped_column(
        enum_column(DiscordConnectionStatus), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )


class DiscordMessage(IdMixin, TimestampMixin, Base):
    """수집한 Discord 메시지 원문. 판단 근거의 source다.

    같은 Discord 메시지는 다시 수집해도 새 행이 아니라 같은 행이다.
    """

    __tablename__ = "discord_messages"
    __id_prefix__ = "dsm"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "message_id", name="uq_discord_messages_connection_message"
        ),
    )

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    connection_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("discord_connections.id"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(String(DISCORD_ID_LENGTH), nullable=False)
    message_id: Mapped[str] = mapped_column(String(DISCORD_ID_LENGTH), nullable=False)
    author_id: Mapped[str | None] = mapped_column(String(DISCORD_ID_LENGTH))
    content: Mapped[str | None] = mapped_column(Text)
    # Discord에서 작성된 시각. 우리가 받은 시각은 created_at이다.
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 마지막으로 반영한 수집 이벤트 id. 같은 이벤트가 다시 와도 두 번 반영하지 않는다.
    last_event_id: Mapped[str | None] = mapped_column(String(100))
