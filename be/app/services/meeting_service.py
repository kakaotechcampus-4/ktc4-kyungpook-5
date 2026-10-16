"""회의 세션·음성 청크·전사 도메인 오케스트레이션 (#135).

최종 전사가 생기면 자동으로 Jev 판단 작업을 만든다(services/context_service.py).
음성 청크의 STT와 판단은 더미다. 실제 작업 큐가 없어 요청 안에서 바로 처리한다.

WebSocket 연결 레지스트리는 프로세스 메모리에만 있다 — 워커가 여러 개면 안 쓰인다.
이번 범위는 단일 개발 서버 기준이라 괜찮다.
"""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentJobKind, AgentJobStage, JudgeRoute, MeetingStatus
from app.core.exceptions import ApiError, VersionConflict
from app.infra.storage import save_file
from app.models.agent import AgentJob, ContextDecision
from app.models.meetings import Meeting, MeetingAudioChunk, TranscriptSegment
from app.services import agent_job_service, context_service
from app.services.meeting_stt_stub import transcribe_chunk

# --- WebSocket 연결 레지스트리 -------------------------------------------

_connections: dict[str, set[WebSocket]] = defaultdict(set)


def register_connection(meeting_id: str, websocket: WebSocket) -> None:
    _connections[meeting_id].add(websocket)


def unregister_connection(meeting_id: str, websocket: WebSocket) -> None:
    _connections[meeting_id].discard(websocket)
    if not _connections[meeting_id]:
        _connections.pop(meeting_id, None)


async def _broadcast(meeting_id: str, message: dict) -> None:
    for ws in list(_connections.get(meeting_id, ())):
        try:
            await ws.send_json(message)
        except Exception:
            # 끊긴 연결 하나 때문에 나머지 구독자한테 보내는 게 막히면 안 된다.
            unregister_connection(meeting_id, ws)


class MeetingNotFound(ApiError):
    status_code = 404
    code = "MEETING_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 회의를 찾을 수 없습니다.")


class MeetingNotRecording(ApiError):
    """종료된 회의에 새 음성·전사를 넣으려 할 때."""

    status_code = 409
    code = "MEETING_NOT_RECORDING"

    def __init__(self) -> None:
        super().__init__("녹음 중인 회의가 아닙니다.")


class ChunkConflict(ApiError):
    """같은 seq로 다른 음성 파일이 왔을 때."""

    status_code = 409
    code = "CHUNK_CONFLICT"

    def __init__(self) -> None:
        super().__init__("같은 순번으로 다른 음성 청크가 이미 올라왔습니다.")


async def create_meeting(
    session: AsyncSession,
    *,
    club_id: str,
    event_id: str | None,
    title: str | None,
    language: str,
    recording_consent_confirmed: bool,
    created_by: str,
) -> Meeting:
    now = datetime.now(UTC)
    meeting = Meeting(
        club_id=club_id,
        event_id=event_id,
        title=title,
        language=language,
        status=MeetingStatus.RECORDING,
        started_at=now,
        recording_consent_confirmed_by=created_by if recording_consent_confirmed else None,
        recording_consent_confirmed_at=now if recording_consent_confirmed else None,
        created_by=created_by,
    )
    session.add(meeting)
    await session.commit()
    return meeting


async def get_meeting(session: AsyncSession, *, club_id: str, meeting_id: str) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None or meeting.club_id != club_id:
        raise MeetingNotFound()
    return meeting


async def finish_meeting(
    session: AsyncSession, *, club_id: str, meeting_id: str
) -> Meeting:
    meeting = await get_meeting(session, club_id=club_id, meeting_id=meeting_id)
    # 음성 청크는 받는 요청 안에서 전사·판단까지 끝나 밀린 처리가 없다 —
    # FINALIZING을 거치지 않고 바로 COMPLETED로 끝난다.
    meeting.status = MeetingStatus.COMPLETED
    meeting.ended_at = datetime.now(UTC)
    await session.commit()
    await _broadcast(
        meeting_id, {"type": "meeting_status", "meetingId": meeting_id, "status": "COMPLETED"}
    )
    return meeting


def _judgment_message(
    segment: TranscriptSegment, job: AgentJob, decision: ContextDecision
) -> dict:
    return {
        "type": "judgment",
        "segmentId": segment.id,
        "seq": segment.seq,
        "sourceVersion": segment.version,
        "jobId": job.id,
        "contextDecisionId": decision.id,
        "route": decision.route.value,
        "kind": decision.kind.value,
        "question": decision.question,
        "answer": decision.output,
        "sources": decision.citations,
        "trace": {
            "model": decision.model_version,
            "promptVersion": decision.policy_version,
            "toolCalls": decision.tool_calls,
        },
    }


async def _save_segment(
    session: AsyncSession,
    meeting: Meeting,
    *,
    seq: int,
    text: str,
    is_final: bool,
    expected_version: int | None,
    speaker_label: str | None,
    start_ms: int | None,
    end_ms: int | None,
    audio_chunk_id: str | None = None,
) -> tuple[TranscriptSegment, ContextDecision | None, list[dict]]:
    """전사를 저장하고 final이면 판단까지 한다. 커밋 뒤 WebSocket으로 보낼 메시지도 돌려준다."""
    existing = await session.scalar(
        select(TranscriptSegment).where(
            TranscriptSegment.meeting_id == meeting.id, TranscriptSegment.seq == seq
        )
    )
    meeting.transcript_cursor += 1

    if existing is None:
        segment = TranscriptSegment(
            meeting_id=meeting.id,
            seq=seq,
            text=text,
            is_final=is_final,
            speaker_label=speaker_label,
            start_ms=start_ms,
            end_ms=end_ms,
            change_seq=meeting.transcript_cursor,
            audio_chunk_id=audio_chunk_id,
        )
        session.add(segment)
    else:
        if expected_version is None or existing.version != expected_version:
            raise VersionConflict()
        segment = existing
        segment.text = text
        segment.is_final = is_final
        segment.speaker_label = speaker_label
        segment.start_ms = start_ms
        segment.end_ms = end_ms
        segment.version += 1
        segment.change_seq = meeting.transcript_cursor
        # 이전 버전으로 한 판단은 최신 결과로 보여주지 않는다. final이면 아래에서 다시 판단한다.
        segment.decision_job_id = None
        await context_service.mark_segment_decisions_stale(
            session, meeting_id=meeting.id, segment_id=segment.id
        )

    await session.flush()
    if not is_final:
        return segment, None, []

    messages = [
        {"type": "stage", "segmentId": segment.id, "seq": segment.seq, "stage": "JUDGING"}
    ]
    job, decision = await context_service.decide_meeting_segment(
        session, meeting=meeting, segment=segment
    )
    if decision.route == JudgeRoute.RAG:
        messages.append(
            {"type": "stage", "segmentId": segment.id, "seq": segment.seq, "stage": "SEARCHING"}
        )
    messages.append(_judgment_message(segment, job, decision))
    return segment, decision, messages


async def submit_transcript(
    session: AsyncSession,
    *,
    club_id: str,
    meeting_id: str,
    seq: int,
    text: str,
    is_final: bool,
    expected_version: int | None,
    speaker_label: str | None,
    start_ms: int | None,
    end_ms: int | None,
) -> TranscriptSegment:
    """실제 Whisper 대신 텍스트를 직접 받는다(test-support). final이면 판단까지 하고
    WebSocket에 결과를 밀어준다."""
    meeting = await get_meeting(session, club_id=club_id, meeting_id=meeting_id)
    if meeting.status != MeetingStatus.RECORDING:
        raise MeetingNotRecording()
    segment, _decision, messages = await _save_segment(
        session,
        meeting,
        seq=seq,
        text=text,
        is_final=is_final,
        expected_version=expected_version,
        speaker_label=speaker_label,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    await session.commit()
    # created_at/modified_at은 DB가 채워 응답 전에 다시 읽는다.
    await session.refresh(segment)
    for message in messages:
        await _broadcast(meeting_id, message)
    return segment


async def add_audio_chunk(
    session: AsyncSession,
    *,
    meeting: Meeting,
    seq: int,
    start_ms: int,
    end_ms: int,
    file_name: str,
    mime_type: str | None,
    content: bytes,
) -> MeetingAudioChunk:
    """음성 청크를 저장하고 더미 STT → 판단까지 처리한다.

    같은 seq·같은 파일 재전송은 처음 결과를 그대로 돌려준다(STT를 다시 돌리지 않는다).
    """
    sha256 = hashlib.sha256(content).hexdigest()
    existing = await session.scalar(
        select(MeetingAudioChunk).where(
            MeetingAudioChunk.meeting_id == meeting.id, MeetingAudioChunk.seq == seq
        )
    )
    if existing is not None:
        if existing.sha256 != sha256:
            raise ChunkConflict()
        return existing
    if meeting.status != MeetingStatus.RECORDING:
        raise MeetingNotRecording()

    job = await agent_job_service.create_job(
        session, club_id=meeting.club_id, kind=AgentJobKind.MEETING_STT
    )
    chunk = MeetingAudioChunk(
        meeting_id=meeting.id,
        seq=seq,
        start_ms=start_ms,
        end_ms=end_ms,
        storage_key=save_file(meeting.club_id, file_name, content),
        sha256=sha256,
        mime_type=mime_type,
        size=len(content),
        job_id=job.id,
    )
    session.add(chunk)
    await session.flush()

    agent_job_service.start(session, job, AgentJobStage.TRANSCRIBING)
    # 전사 순번은 청크 seq와 다른 축이다. 회의 안에서 이어 붙인다.
    last_seq = await session.scalar(
        select(func.max(TranscriptSegment.seq)).where(
            TranscriptSegment.meeting_id == meeting.id
        )
    )
    segment, decision, messages = await _save_segment(
        session,
        meeting,
        seq=(last_seq or 0) + 1,
        text=transcribe_chunk(seq=seq, start_ms=start_ms, end_ms=end_ms),
        is_final=True,
        expected_version=None,
        speaker_label=None,
        start_ms=start_ms,
        end_ms=end_ms,
        audio_chunk_id=chunk.id,
    )
    agent_job_service.succeed(
        session,
        job,
        {
            "audioChunkId": chunk.id,
            "segmentIds": [segment.id],
            "contextDecisionIds": [decision.id] if decision else [],
        },
    )
    await session.commit()
    for message in messages:
        await _broadcast(meeting.id, message)
    return chunk


async def list_transcripts(
    session: AsyncSession, *, meeting_id: str, after_seq: int
) -> list[TranscriptSegment]:
    """after_seq 이후에 생기거나 고쳐진 전사. 고친 전사도 다시 나온다."""
    return list(
        await session.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.meeting_id == meeting_id,
                TranscriptSegment.change_seq > after_seq,
            )
            .order_by(TranscriptSegment.change_seq)
        )
    )
