"""회의 세션·전사 도메인 요청·응답 스키마 (#135)."""

from app.core.enums import MeetingStatus
from app.schemas.common import CamelModel, UtcDateTime


class MeetingCreateIn(CamelModel):
    title: str | None = None
    language: str = "ko-KR"
    recording_consent_confirmed: bool
    event_id: str | None = None


class MeetingOut(CamelModel):
    id: str
    title: str | None
    language: str
    status: MeetingStatus
    started_at: UtcDateTime | None
    ended_at: UtcDateTime | None
    version: int


class TranscriptSegmentOut(CamelModel):
    id: str
    # 판단 근거로 참조할 때의 원문 id·버전. 지금은 전사 id·version과 같다.
    source_id: str
    source_version: int
    seq: int
    text: str
    final: bool
    version: int
    speaker_label: str | None
    start_ms: int | None
    end_ms: int | None
    # 현재 version에 대한 판단 작업. final이 아니면 null.
    decision_job_id: str | None
    created_at: UtcDateTime
    modified_at: UtcDateTime


class TranscriptListOut(CamelModel):
    # 다음 조회의 afterSeq로 넘길 값.
    cursor: int
    items: list[TranscriptSegmentOut]


class AudioChunkOut(CamelModel):
    chunk_id: str
    seq: int
    job_id: str


class TestSupportTranscriptOut(TranscriptSegmentOut):
    # 자동으로 생긴 판단 작업. decisionJobId와 같다.
    job_id: str | None


class TestSupportTranscriptIn(CamelModel):
    """실제 Whisper 없이 전사 텍스트를 직접 주입한다 (meeting.curl.sh M05와 동일한 패턴)."""

    seq: int
    start_ms: int
    end_ms: int
    final: bool
    text: str
    speaker_label: str | None = None
    # 같은 seq를 다시 보낼 때(정정)만 필요하다.
    expected_version: int | None = None
