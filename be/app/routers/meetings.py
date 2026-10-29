"""회의 세션 엔드포인트 (#135).

WS PCM 연속 음성은 BE VAD·실제 STT를 거쳐 확정 전사·AI로 연결된다.
기존 HTTP 청크는 개발용 더미 STT 경로이며 실제 음성 베타에 사용하지 않는다.
"""

from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import (
    ensure_member,
    get_current_account,
    require_member,
    resolve_account_by_token,
)
from app.core.enums import MeetingStatus
from app.core.exceptions import Forbidden
from app.db.session import get_session, get_sessionmaker
from app.infra.stt import SttError, WhisperStt, pcm_to_wav
from app.models.auth import Account
from app.models.clubs import Member
from app.models.meetings import Meeting, MeetingAudioChunk, TranscriptSegment
from app.schemas.common import Envelope
from app.schemas.meetings import (
    AudioChunkOut,
    MeetingCreateIn,
    MeetingOut,
    TranscriptListOut,
    TranscriptSegmentOut,
)
from app.services import meeting_service
from app.services.audio_stream_service import AudioProtocolError, AudioStream, Utterance

router = APIRouter(tags=["meetings"])


def _meeting_out(meeting: Meeting) -> MeetingOut:
    return MeetingOut(
        id=meeting.id,
        club_id=meeting.club_id,
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
    seq: int = Form(..., ge=1),
    start_ms: int = Form(..., alias="startMs", ge=0),
    end_ms: int = Form(..., alias="endMs", ge=0),
    file: UploadFile = File(...),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[AudioChunkOut]:
    meeting = await _get_meeting_for_account(session, meeting_id=meeting_id, account=account)
    if not get_settings().test_mode:
        raise meeting_service.HttpAudioNotImplemented()
    chunk = await meeting_service.add_audio_chunk(
        session,
        meeting=meeting,
        seq=seq,
        start_ms=start_ms,
        end_ms=end_ms,
        file_name=file.filename or f"chunk-{seq}",
        mime_type=file.content_type,
        content=await file.read(),
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
    """Authenticated subscriber + optional single PCM producer. See docs/meeting-audio.md.

    Browser WebSocket cannot send Authorization headers, so the existing opaque
    session token is accepted in the query. No token is echoed in stream events.
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

    language = meeting.language
    # The websocket can last hours. Do not retain its authentication DB transaction.
    await session.rollback()
    await websocket.accept()
    meeting_service.register_connection(meeting_id, websocket)
    provider: WhisperStt | None = None
    stream_offset_ms = 0

    async def start() -> int:
        nonlocal provider, stream_offset_ms
        # The agreed start frame has no client capture timestamp. Use server
        # receipt time before the DB lookup; network/handshake latency is included.
        start_received_at = datetime.now(UTC)
        async with get_sessionmaker()() as check_session:
            current = await check_session.get(Meeting, meeting_id)
            if current is None or current.status != MeetingStatus.RECORDING:
                raise AudioProtocolError("MEETING_NOT_RECORDING", "녹음 중인 회의가 아닙니다.")
            if current.recording_consent_confirmed_at is None:
                raise AudioProtocolError("RECORDING_CONSENT_REQUIRED", "참여자 녹음 동의를 확인한 회의만 녹음할 수 있습니다.")
            prior_chunk = await check_session.scalar(
                select(MeetingAudioChunk.id)
                .where(MeetingAudioChunk.meeting_id == meeting_id)
                .limit(1)
            )
            if prior_chunk is not None:
                raise AudioProtocolError(
                    "AUDIO_RESUME_UNSUPPORTED",
                    "이 회의의 저장된 전사를 확인하고 새 회의에서 녹음해 주세요.",
                )
            if current.started_at is not None:
                stream_offset_ms = max(
                    0, int((start_received_at - current.started_at).total_seconds() * 1000)
                )
        settings = get_settings()
        provider = WhisperStt(
            url=settings.stt_url, api_key=settings.stt_api_key.get_secret_value(),
            model=settings.stt_model, timeout_seconds=settings.stt_timeout_seconds,
        )
        return stream_offset_ms

    async def transcribe(utterance: Utterance) -> str | None:
        wav = pcm_to_wav(utterance.pcm)
        # Audio metadata remains stream-relative; persisted evidence uses the
        # meeting.startedAt timeline shared with AI and the FE timeline.
        start_ms = stream_offset_ms + utterance.start_ms
        end_ms = stream_offset_ms + utterance.end_ms
        async with get_sessionmaker()() as worker_session:
            chunk_id, job_id = await meeting_service.begin_stream_utterance(
                worker_session, meeting_id=meeting_id, wav=wav,
                start_ms=start_ms, end_ms=end_ms,
            )
        try:
            assert provider is not None
            text = await provider.transcribe(wav, language=language)
            async with get_sessionmaker()() as worker_session:
                return await meeting_service.save_stream_transcript(
                    worker_session, meeting_id=meeting_id, chunk_id=chunk_id, job_id=job_id,
                    text=text, start_ms=start_ms, end_ms=end_ms,
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, SttError) else "AUDIO_PERSISTENCE_FAILED"
            message = exc.message if isinstance(exc, SttError) else "확정 전사를 저장하지 못했습니다."
            async with get_sessionmaker()() as worker_session:
                await meeting_service.fail_stream_stt(worker_session, job_id=job_id, code=code, message=message)
            raise

    async def decide(segment_id: str) -> None:
        async with get_sessionmaker()() as worker_session:
            await meeting_service.process_saved_segment(worker_session, meeting_id=meeting_id, segment_id=segment_id)

    async def begin_finalizing() -> None:
        async with get_sessionmaker()() as worker_session:
            await meeting_service.set_stream_status(worker_session, meeting_id=meeting_id, status=MeetingStatus.FINALIZING)

    async def finalize(success: bool) -> None:
        async with get_sessionmaker()() as worker_session:
            await meeting_service.set_stream_status(worker_session, meeting_id=meeting_id, status=MeetingStatus.COMPLETED if success else MeetingStatus.FAILED)

    try:
        await AudioStream(
            meeting_id=meeting_id, websocket=websocket, start=start,
            transcribe=transcribe, decide=decide, finalize=finalize,
            begin_finalizing=begin_finalizing,
            rms_threshold=get_settings().audio_vad_rms_threshold,
        ).run()
    except WebSocketDisconnect:
        pass
    finally:
        meeting_service.unregister_connection(meeting_id, websocket)
