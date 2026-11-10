import io
import wave

import pytest

from app.infra.meeting_audio import assemble_meeting_wav


def _chunk(start: int, end: int, value: bytes = b"\x01\x00") -> bytes:
    raw = value * ((end - start) * 16)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(raw)
    return output.getvalue()


def _frames(data: bytes) -> bytes:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.readframes(wav.getnframes())


def test_reconstructs_original_timeline_and_zero_fills_gaps():
    output = io.BytesIO()
    duration = assemble_meeting_wav([(0, 100, _chunk(0, 100, b"\x01\x00")), (200, 300, _chunk(200, 300, b"\x02\x00"))], output)
    frames = _frames(output.getvalue())
    assert duration == 300
    assert len(frames) == 300 * 32
    assert frames[:2] == b"\x01\x00"
    assert frames[100 * 32:200 * 32] == b"\x00" * (100 * 32)
    assert frames[-2:] == b"\x02\x00"


@pytest.mark.parametrize("chunks", [
    [(200, 100, b"")],
    [(0, 200, _chunk(0, 100))],
    [(100, 200, _chunk(100, 200)), (150, 250, _chunk(150, 250))],
])
def test_rejects_malformed_or_overlapping_chunks(chunks):
    with pytest.raises(ValueError):
        assemble_meeting_wav(chunks, io.BytesIO())


def test_no_chunks_raises_korean_message():
    """발화 전부가 STT 전에 저장 자체를 실패한 FAILED 회의처럼, 오디오가 한 건도
    없으면 라우터가 그대로 ReviewConflict로 보여줄 한국어 메시지를 낸다."""
    with pytest.raises(ValueError, match="저장된 회의 음성이 없어요"):
        assemble_meeting_wav([], io.BytesIO())
