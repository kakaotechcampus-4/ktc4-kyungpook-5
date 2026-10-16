"""TEST_MODE 전용 우회 엔드포인트.

브라우저 동의 화면 등 curl로 재현할 수 없는 경로를 테스트용으로 대신한다.
main.py에서 settings.test_mode가 true일 때만 이 라우터를 등록한다 — 운영
환경에는 이 모듈 자체가 올라가지 않으므로 404가 아니라 아예 라우트가 없다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_member
from app.core.exceptions import ValidationFailed
from app.db.session import get_session
from app.models.clubs import Member
from app.schemas.auth import KakaoLoginIn, SessionOut
from app.schemas.common import Envelope
from app.schemas.meetings import TestSupportTranscriptIn, TranscriptSegmentOut
from app.services import auth_service, meeting_service

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
    response_model=Envelope[TranscriptSegmentOut],
    status_code=201,
)
async def inject_transcript(
    club_id: str,
    meeting_id: str,
    body: TestSupportTranscriptIn,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TranscriptSegmentOut]:
    """실제 Whisper 없이 전사 텍스트를 직접 주입한다 (meeting.curl.sh M05).

    final이면 더미 판단(services/meeting_judge_stub.py)까지 바로 돌아가고,
    연결된 WebSocket이 있으면 결과가 그쪽으로도 나간다.
    """
    segment = await meeting_service.submit_transcript(
        session,
        club_id=club_id,
        meeting_id=meeting_id,
        seq=body.seq,
        text=body.text,
        is_final=body.final,
        expected_version=body.expected_version,
    )
    return Envelope(
        data=TranscriptSegmentOut(
            id=segment.id,
            seq=segment.seq,
            text=segment.text,
            final=segment.is_final,
            version=segment.version,
            route=segment.route,
            kind=segment.kind,
            question=segment.question,
            answer=segment.answer,
            sources=segment.sources,
            trace=segment.trace,
        )
    )
