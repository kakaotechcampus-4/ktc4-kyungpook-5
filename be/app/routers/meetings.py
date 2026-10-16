"""회의 세션 엔드포인트 (#135).

실제 오디오는 받지 않는다 — WebSocket은 세션·결과 전송 채널의 모양만
증명한다. 전사는 test_support.py의 더미 주입 경로로 넣는다.
"""

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_account, require_member, resolve_account_by_token
from app.core.exceptions import Forbidden
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.meetings import Meeting
from app.schemas.common import Envelope
from app.schemas.meetings import MeetingCreateIn, MeetingOut
from app.services import meeting_service

router = APIRouter(tags=["meetings"])


def _meeting_out(meeting: Meeting) -> MeetingOut:
    return MeetingOut(
        id=meeting.id,
        title=meeting.title,
        language=meeting.language,
        status=meeting.status,
        started_at=meeting.started_at,
        ended_at=meeting.ended_at,
        version=meeting.version,
    )


async def _get_meeting_for_account(
    session: AsyncSession, *, meeting_id: str, account: Account
) -> Meeting:
    """club_id가 URL에 없는 라우트(/meetings/{id}, .../finish)용.

    require_member는 경로의 club_id를 전제로 하는 의존성이라 여기엔 못 쓴다.
    """
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise meeting_service.MeetingNotFound()
    member = await session.scalar(
        select(Member).where(
            Member.club_id == meeting.club_id, Member.account_id == account.id
        )
    )
    if member is None:
        raise Forbidden("이 동아리에 속한 운영진만 할 수 있습니다.")
    return meeting


@router.post(
    "/api/v1/clubs/{club_id}/meetings",
    response_model=Envelope[MeetingOut],
    status_code=201,
)
async def create_meeting(
    club_id: str,
    body: MeetingCreateIn,
    member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[MeetingOut]:
    meeting = await meeting_service.create_meeting(
        session,
        club_id=club_id,
        event_id=body.event_id,
        title=body.title,
        language=body.language,
        recording_consent_confirmed=body.recording_consent_confirmed,
        created_by=member.id,
    )
    return Envelope(data=_meeting_out(meeting))


@router.get("/api/v1/meetings/{meeting_id}", response_model=Envelope[MeetingOut])
async def get_meeting(
    meeting_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[MeetingOut]:
    meeting = await _get_meeting_for_account(session, meeting_id=meeting_id, account=account)
    return Envelope(data=_meeting_out(meeting))


@router.post(
    "/api/v1/meetings/{meeting_id}/finish", response_model=Envelope[MeetingOut]
)
async def finish_meeting(
    meeting_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[MeetingOut]:
    meeting = await _get_meeting_for_account(session, meeting_id=meeting_id, account=account)
    updated = await meeting_service.finish_meeting(
        session, club_id=meeting.club_id, meeting_id=meeting_id
    )
    return Envelope(data=_meeting_out(updated))


@router.websocket("/api/v1/meetings/{meeting_id}/stream")
async def meeting_stream(
    websocket: WebSocket,
    meeting_id: str,
    token: str = Query(...),
    session: AsyncSession = Depends(get_session),
) -> None:
    """오디오 bytes를 받긴 하지만 지금은 버린다 — 채널이 실제로 여닫히고,
    결과가 같은 연결로 내려가는 것만 증명한다. 실제 처리는 test-support로
    주입한 전사가 트리거한다.

    브라우저 WebSocket은 커스텀 헤더를 못 보내 토큰을 쿼리 파라미터로 받는다.
    """
    account = await resolve_account_by_token(token, session)
    if account is None:
        await websocket.close(code=4401)
        return

    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        await websocket.close(code=4404)
        return

    member = await session.scalar(
        select(Member).where(
            Member.club_id == meeting.club_id, Member.account_id == account.id
        )
    )
    if member is None:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    meeting_service.register_connection(meeting_id, websocket)
    try:
        while True:
            # 오디오 프레임을 받아도 지금은 처리하지 않는다 (VAD·Whisper는 후속 이슈).
            await websocket.receive_bytes()
    except WebSocketDisconnect:
        pass
    finally:
        meeting_service.unregister_connection(meeting_id, websocket)
