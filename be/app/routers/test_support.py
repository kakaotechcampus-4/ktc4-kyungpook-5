"""TEST_MODE 전용 우회 엔드포인트.

브라우저 동의 화면 등 curl로 재현할 수 없는 경로를 테스트용으로 대신한다.
main.py에서 settings.test_mode가 true일 때만 이 라우터를 등록한다 — 운영
환경에는 이 모듈 자체가 올라가지 않으므로 404가 아니라 아예 라우트가 없다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import WRITER_ROLES, require_club_role, require_member
from app.core.enums import DiscordConnectionMode
from app.core.exceptions import ValidationFailed
from app.db.session import get_session
from app.models.clubs import Member
from app.routers.meetings import transcript_out
from app.schemas.auth import KakaoLoginIn, SessionOut
from app.schemas.common import Envelope
from app.schemas.discord import (
    DiscordConnectionOut,
    FixtureConnectionCreateIn,
    FixtureDiscordEventIn,
    FixtureDiscordEventOut,
)
from app.schemas.meetings import TestSupportTranscriptIn, TestSupportTranscriptOut
from app.services import auth_service, discord_service, meeting_service

router = APIRouter(prefix="/api/v1/test-support", tags=["test-support"])


@router.post("/auth/kakao-login", response_model=Envelope[SessionOut], status_code=201)
async def kakao_login_bypass(
    body: KakaoLoginIn, session: AsyncSession = Depends(get_session)
) -> Envelope[SessionOut]:
    """카카오 동의 화면 없이 테스트 프로필로 바로 세션을 발급한다."""
    if not body.kakao_user_id or not body.email:
        raise ValidationFailed(
            {"kakaoUserId": "kakaoUserId·email이 필요합니다."}
        )
    access_token, refresh_token = await auth_service.login_with_kakao(
        session, kakao_user_id=body.kakao_user_id, email=body.email
    )
    return Envelope(
        data=SessionOut(access_token=access_token, refresh_token=refresh_token)
    )


@router.post(
    "/clubs/{club_id}/meetings/{meeting_id}/transcripts",
    response_model=Envelope[TestSupportTranscriptOut],
    status_code=201,
)
async def inject_transcript(
    club_id: str,
    meeting_id: str,
    body: TestSupportTranscriptIn,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TestSupportTranscriptOut]:
    """실제 Whisper 없이 전사 텍스트를 직접 주입한다 (meeting.curl.sh M05).

    STT가 만든 전사와 같은 경로(meeting_service)로 저장한다. final이면 판단 작업이
    자동으로 생기고, 연결된 WebSocket이 있으면 결과가 그쪽으로도 나간다.
    분기를 입력으로 지정하지 않는다 — 판단은 문장만 보고 한다.
    """
    segment = await meeting_service.submit_transcript(
        session,
        club_id=club_id,
        meeting_id=meeting_id,
        seq=body.seq,
        text=body.text,
        is_final=body.final,
        expected_version=body.expected_version,
        speaker_label=body.speaker_label,
        start_ms=body.start_ms,
        end_ms=body.end_ms,
    )
    return Envelope(
        data=TestSupportTranscriptOut(
            **transcript_out(segment), job_id=segment.decision_job_id
        )
    )


@router.post(
    "/clubs/{club_id}/discord-connections",
    response_model=Envelope[DiscordConnectionOut],
    status_code=201,
)
async def create_fixture_connection(
    club_id: str,
    body: FixtureConnectionCreateIn,
    member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[DiscordConnectionOut]:
    """실제 bot credential 없이 이벤트 주입용 연결을 만든다. 외부 Discord에 접속하지 않는다."""
    if body.mode != DiscordConnectionMode.FIXTURE:
        raise ValidationFailed({"mode": "test-support 경로는 FIXTURE 연결만 만듭니다."})
    connection = await discord_service.create_connection(
        session,
        club_id=club_id,
        mode=DiscordConnectionMode.FIXTURE,
        guild_id=body.guild_id,
        channel_ids=body.channel_ids,
        bot_profile=None,
        enabled=body.enabled,
        created_by=member.id,
    )
    return Envelope(data=DiscordConnectionOut.model_validate(connection))


@router.post(
    "/clubs/{club_id}/discord-events",
    response_model=Envelope[FixtureDiscordEventOut],
    status_code=202,
)
async def inject_discord_event(
    club_id: str,
    body: FixtureDiscordEventIn,
    _member: Member = Depends(require_club_role(*WRITER_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[FixtureDiscordEventOut]:
    """수집기가 받은 Discord 이벤트를 흉내 낸다. 메시지를 외부로 보내지 않는다."""
    message, job = await discord_service.ingest_fixture_event(
        session, club_id=club_id, event=body
    )
    return Envelope(
        data=FixtureDiscordEventOut(
            event_id=body.event_id,
            message_id=message.id,
            source_version=message.version,
            duplicate=job is None,
            job_id=job.id if job else None,
        )
    )
