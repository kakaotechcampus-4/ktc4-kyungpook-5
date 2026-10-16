"""Discord 연결·메시지 요청·응답 스키마. Discord ID는 모두 문자열이다."""

from datetime import datetime

from pydantic import Field

from app.core.enums import DiscordConnectionMode, DiscordConnectionStatus
from app.schemas.common import CamelModel, UtcDateTime


class DiscordConnectionCreateIn(CamelModel):
    guild_id: str
    channel_ids: list[str] = Field(min_length=1)
    # 서버 환경에 등록한 bot 설정 이름. token이 아니다.
    bot_profile: str
    enabled: bool = True


class FixtureConnectionCreateIn(CamelModel):
    mode: DiscordConnectionMode
    guild_id: str
    channel_ids: list[str] = Field(min_length=1)
    enabled: bool = True


class DiscordConnectionPatchIn(CamelModel):
    expected_version: int
    enabled: bool | None = None
    channel_ids: list[str] | None = Field(None, min_length=1)


class DiscordConnectionOut(CamelModel):
    id: str
    mode: DiscordConnectionMode
    guild_id: str
    channel_ids: list[str]
    bot_profile: str | None
    enabled: bool
    status: DiscordConnectionStatus
    version: int
    created_at: UtcDateTime


class DiscordMessageOut(CamelModel):
    id: str
    # 판단 근거로 참조할 때의 원문 id·버전
    source_id: str
    source_version: int
    channel_id: str
    message_id: str
    author_id: str | None
    content: str | None
    posted_at: UtcDateTime | None
    # 우리 시스템이 받은 시각
    created_at: UtcDateTime


class DiscordSyncOut(CamelModel):
    job_id: str


class FixtureDiscordEventIn(CamelModel):
    connection_id: str
    event_type: str
    event_id: str
    guild_id: str
    channel_id: str
    message_id: str
    author_id: str | None = None
    source_occurred_at: datetime
    content: str | None = None


class FixtureDiscordEventOut(CamelModel):
    event_id: str
    # 내부 메시지 id(sourceId)
    message_id: str
    source_version: int
    # 이미 받은 이벤트·메시지면 true. 새 판단을 만들지 않는다.
    duplicate: bool
    # 이 이벤트로 시작한 판단 작업. duplicate면 null.
    job_id: str | None
