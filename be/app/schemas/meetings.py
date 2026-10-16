"""회의 세션·전사 도메인 요청·응답 스키마 (#135)."""

from typing import Any

from app.core.enums import JudgeKind, JudgeRoute, MeetingStatus
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
    seq: int
    text: str
    final: bool
    version: int
    route: JudgeRoute | None
    kind: JudgeKind | None
    question: str | None
    answer: str | None
    sources: list[dict[str, Any]] | None
    trace: dict[str, Any] | None


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
