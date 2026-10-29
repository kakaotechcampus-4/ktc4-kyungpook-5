"""회의 세션 엔드포인트 (#135).

음성 청크는 HTTP로 받아 저장하고 더미 STT로 전사를 만든다. WebSocket은 판단 결과를
실시간으로 받는 채널이며, 오디오 프레임은 아직 처리하지 않는다. 테스트용 전사는
test_support.py의 주입 경로로 넣는다.
"""

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    ensure_member,
    get_current_account,
    require_member,
    resolve_account_by_token,
)
from app.core.exceptions import Forbidden
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.meetings import Meeting, TranscriptSegment
from app.schemas.common import Envelope
from app.schemas.meetings import (
    AudioChunkOut,
    MeetingCreateIn,
    MeetingOut,
    TranscriptListOut,
    TranscriptSegmentOut,
)
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


def transcript_out(segment: TranscriptSegment) -> dict:
    """TranscriptSegmentOut과 test-support 응답이 함께 쓰는 필드."""
    return {
        "id": segment.id,
        "source_id": segment.id,
        "source_version": segment.version,
        "seq": segment.seq,
        "text": segment.text,
        "final": segment.is_final,
        "version": segment.version,
        "speaker_label": segment.speaker_label,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "decision_job_id": segment.decision_job_id,
        "created_at": segment.created_at,
        "modified_at": segment.modified_at,
    }


async def _get_meeting_for_account(
    session: AsyncSession, *, meeting_id: str, account: Account
) -> Meeting:
    """club_id가 URL에 없는 라우트용. 회의를 찾은 뒤 그 동아리 소속인지 본다."""
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise meeting_service.MeetingNotFound()
    await ensure_member(session, club_id=meeting.club_id, account=account)
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
    "/api/v1/meetings/{meeting_id}/audio-chunks",
    response_model=Envelope[AudioChunkOut],
    status_code=202,
)
async def upload_audio_chunk(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    seq: int = Form(..., ge=1),
    start_ms: int = Form(..., alias="startMs", ge=0),
    end_ms: int = Form(..., alias="endMs", ge=0),
    file: UploadFile = File(...),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[AudioChunkOut]:
    meeting = await _get_meeting_for_account(session, meeting_id=meeting_id, account=account)
    chunk = await meeting_service.add_audio_chunk(
        session,
        meeting=meeting,
        seq=seq,
        start_ms=start_ms,
        end_ms=end_ms,
        file_name=file.filename or f"chunk-{seq}",
        mime_type=file.content_type,
        content=await file.read(),
        background_tasks=background_tasks,
    )
    return Envelope(data=AudioChunkOut(chunk_id=chunk.id, seq=chunk.seq, job_id=chunk.job_id))


@router.get(
    "/api/v1/meetings/{meeting_id}/transcripts",
    response_model=Envelope[TranscriptListOut],
)
async def list_transcripts(
    meeting_id: str,
    after_seq: int = Query(0, alias="afterSeq", ge=0),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[TranscriptListOut]:
    meeting = await _get_meeting_for_account(session, meeting_id=meeting_id, account=account)
    segments = await meeting_service.list_transcripts(
        session, meeting_id=meeting.id, after_seq=after_seq
    )
    return Envelope(
        data=TranscriptListOut(
            cursor=meeting.transcript_cursor,
            items=[TranscriptSegmentOut(**transcript_out(segment)) for segment in segments],
        )
    )


@router.post(
    "/api/v1/meetings/{meeting_id}/finish",
    response_model=Envelope[MeetingOut],
    status_code=202,
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
    """판단 결과가 같은 연결로 내려간다. 오디오 bytes를 받긴 하지만 지금은 버린다 —
    음성은 HTTP audio-chunks로 받는다.

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

    try:
        await ensure_member(session, club_id=meeting.club_id, account=account)
    except Forbidden:
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
