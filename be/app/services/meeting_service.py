"""회의 세션·음성 청크·전사 도메인 오케스트레이션 (#135 → #141).

최종 전사가 생기면 Jev 판단 작업을 백그라운드로 돌린다(services/context_service.py).
실제 판단은 검색까지 하면 수 초 걸려(#141), 요청 안에서 기다리면 다음 발화 처리가
밀린다 — 그래서 FastAPI BackgroundTasks로 따로 실행하고, 끝나면 WebSocket으로
결과를 보낸다. 이 프로젝트엔 작업 큐가 없어 택한 방식이다(개발 서버 단일 프로세스
기준). asyncio.create_task는 쓰지 않는다 — anyio 구조적 동시성에서 요청 범위를
벗어나면 취소될 수 있어(테스트 클라이언트에서 실제로 재현됨), BackgroundTasks를
쓴다.

음성 청크의 STT는 아직 더미다(#118).

WebSocket 연결 레지스트리는 프로세스 메모리에만 있다 — 워커가 여러 개면 안 쓰인다.
이번 범위는 단일 개발 서버 기준이라 괜찮다.
"""

import hashlib
import logging
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import BackgroundTasks, WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentJobKind, AgentJobStage, MeetingStatus
from app.core.exceptions import ApiError, VersionConflict
from app.db.session import get_sessionmaker
from app.infra.storage import save_file
from app.models.agent import AgentJob, ContextDecision
from app.models.meetings import Meeting, MeetingAudioChunk, TranscriptSegment
from app.services import agent_job_service, context_service
from app.services.meeting_stt_stub import transcribe_chunk

# --- WebSocket 연결 레지스트리 -------------------------------------------

logger = logging.getLogger(__name__)

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
    # 이미 끝난 회의를 다시 끝내면 ended_at이 덮어써지고 종료 알림이 중복된다.
    if meeting.status != MeetingStatus.RECORDING:
        raise MeetingNotRecording()
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
        "status": decision.status.value,
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


class _WsMeetingProgress:
    """app.ai.MeetingProgressPort 구현체. AI가 실제로 그 단계에 들어갈 때만 보낸다
    (예전처럼 route를 보고 BE가 추측해서 SEARCHING을 미리 보내지 않는다)."""

    def __init__(self, meeting_id: str, segment_id: str, seq: int) -> None:
        self._meeting_id = meeting_id
        self._segment_id = segment_id
        self._seq = seq

    async def stage_changed(self, utterance_id: str, stage: str) -> None:
        await _broadcast(
            self._meeting_id,
            {
                "type": "stage",
                "segmentId": self._segment_id,
                "seq": self._seq,
                "stage": stage,
            },
        )


async def _judge_in_background(meeting_id: str, segment_id: str, seq: int) -> None:
    """요청과 무관한 자기 세션으로 판단을 돌린다 — AI 호출 중 요청 세션을 쥐지 않기
    위해서다(db/session.py, #187에서 확인). 늦게 끝나도 결과를 버리지 않는다."""
    try:
        async with get_sessionmaker()() as session:
            meeting = await session.get(Meeting, meeting_id)
            segment = await session.get(TranscriptSegment, segment_id)
            if meeting is None or segment is None:
                return
            job, decision = await context_service.decide_meeting_segment(
                session, meeting=meeting, segment=segment,
                progress=_WsMeetingProgress(meeting_id, segment_id, seq),
            )
            await session.commit()
            await session.refresh(segment)
        await _broadcast(meeting_id, _judgment_message(segment, job, decision))
    except Exception:
        # app.ai.AIError는 context_service 안에서 이미 FAILED로 기록하고 돌아온다.
        # 여기 걸리는 건 BE 쪽 예상 못 한 예외다 — 그래도 화면이 무한정 기다리지
        # 않도록 알린다.
        logger.exception(
            "meeting judgment background task failed meeting_id=%s segment_id=%s",
            meeting_id, segment_id,
        )
        await _broadcast(
            meeting_id,
            {"type": "judgment_failed", "segmentId": segment_id, "seq": seq},
        )


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
) -> TranscriptSegment:
    """전사를 저장한다. final이어도 판단은 여기서 하지 않는다 — 호출한 쪽이 커밋한
    뒤 판단을 백그라운드로 따로 건다(#141, _judge_in_background 참고)."""
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
    return segment


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
    """실제 Whisper 대신 텍스트를 직접 받는다(test-support 전용 — 실제 라우터는
    add_audio_chunk만 쓴다). 테스트가 결과를 바로 확인할 수 있도록 판단을 요청 안에서
    동기로 끝낸다 — 백그라운드(add_audio_chunk 쪽)와 달리 여기선 커넥션을 오래
    쥐는 게 문제되지 않는다(테스트 전용 경로, 동시 요청이 없다)."""
    meeting = await get_meeting(session, club_id=club_id, meeting_id=meeting_id)
    if meeting.status != MeetingStatus.RECORDING:
        raise MeetingNotRecording()
    segment = await _save_segment(
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
    job = decision = None
    if is_final:
        job, decision = await context_service.decide_meeting_segment(
            session, meeting=meeting, segment=segment,
            progress=_WsMeetingProgress(meeting_id, segment.id, segment.seq),
        )
    await session.commit()
    # created_at/modified_at, decision_job_id는 DB가 채워 응답 전에 다시 읽는다.
    await session.refresh(segment)
    if job is not None and decision is not None:
        await _broadcast(meeting_id, _judgment_message(segment, job, decision))
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
    background_tasks: BackgroundTasks,
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
    segment = await _save_segment(
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
    # 판단(CONTEXT_DECISION)은 별도 작업이라 여기 STT 작업 결과엔 안 담는다 —
    # 백그라운드로 돌아 이 요청 안에서는 아직 모른다.
    agent_job_service.succeed(
        session, job, {"audioChunkId": chunk.id, "segmentIds": [segment.id]}
    )
    await session.commit()
    # FastAPI BackgroundTasks를 쓴다 — asyncio.create_task는 요청 범위를 벗어나면
    # 취소될 수 있다(anyio 구조적 동시성). BackgroundTasks는 응답을 보낸 뒤에도
    # 요청 수명 안에서 끝까지 돈다.
    background_tasks.add_task(_judge_in_background, meeting.id, segment.id, segment.seq)
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
