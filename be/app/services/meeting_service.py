"""회의 세션·전사 도메인 오케스트레이션 (#135).

판단은 더미(meeting_judge_stub)로 채운다. WebSocket 연결 레지스트리는
프로세스 메모리에만 있다 — 워커가 여러 개면 안 쓰인다. 이번 범위는 단일
개발 서버 기준이라 괜찮다.
"""

from collections import defaultdict
from datetime import UTC, datetime

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MeetingStatus
from app.core.exceptions import ApiError, VersionConflict
from app.models.meetings import Meeting, TranscriptSegment
from app.services.meeting_judge_stub import judge_utterance_stub

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
    # 실제 오디오·STT 큐가 없어 밀린 처리가 없다 — 바로 COMPLETED로 끝난다.
    meeting.status = MeetingStatus.COMPLETED
    meeting.ended_at = datetime.now(UTC)
    await session.commit()
    await _broadcast(
        meeting_id, {"type": "meeting_status", "meetingId": meeting_id, "status": "COMPLETED"}
    )
    return meeting


async def submit_transcript(
    session: AsyncSession,
    *,
    club_id: str,
    meeting_id: str,
    seq: int,
    text: str,
    is_final: bool,
    expected_version: int | None,
) -> TranscriptSegment:
    """실제 Whisper 대신 텍스트를 직접 받는다. final이면 더미 판단을 돌리고
    WebSocket에 결과를 밀어준다."""
    await get_meeting(session, club_id=club_id, meeting_id=meeting_id)

    existing = await session.scalar(
        select(TranscriptSegment).where(
            TranscriptSegment.meeting_id == meeting_id, TranscriptSegment.seq == seq
        )
    )

    if existing is None:
        segment = TranscriptSegment(
            meeting_id=meeting_id, seq=seq, text=text, is_final=is_final
        )
        session.add(segment)
    else:
        if expected_version is None or existing.version != expected_version:
            raise VersionConflict()
        segment = existing
        segment.text = text
        segment.is_final = is_final
        segment.version += 1
        # 전사가 정정되면 이전 판단은 더 이상 유효하지 않다 — 다시 판단할 때까지 비운다.
        segment.route = None
        segment.kind = None
        segment.question = None
        segment.answer = None
        segment.sources = None
        segment.trace = None

    await session.flush()

    if is_final:
        await _broadcast(
            meeting_id,
            {
                "type": "stage",
                "segmentId": segment.id,
                "seq": segment.seq,
                "stage": "JUDGING",
            },
        )
        result = judge_utterance_stub(text)
        if result.route.value == "RAG":
            await _broadcast(
                meeting_id,
                {
                    "type": "stage",
                    "segmentId": segment.id,
                    "seq": segment.seq,
                    "stage": "SEARCHING",
                },
            )
        segment.route = result.route
        segment.kind = result.kind
        segment.question = result.question
        segment.answer = result.answer
        segment.sources = result.sources
        segment.trace = result.trace

    await session.commit()
    await session.refresh(segment)

    if is_final:
        await _broadcast(
            meeting_id,
            {
                "type": "judgment",
                "segmentId": segment.id,
                "seq": segment.seq,
                "sourceVersion": segment.version,
                "route": segment.route.value if segment.route else None,
                "kind": segment.kind.value if segment.kind else None,
                "question": segment.question,
                "answer": segment.answer,
                "sources": segment.sources,
                "trace": segment.trace,
            },
        )

    return segment
