"""PCM/VAD, end-tail drain, provider failures and independent STT/AI execution."""

import asyncio
import json
import struct
import uuid

import httpx
import pytest

from app.infra.stt import SttError, WhisperStt, pcm_to_wav
from app.services.audio_stream_service import AudioStream, PcmVad, Utterance, is_recording

pytestmark = pytest.mark.anyio


def pcm(ms: int, amplitude: int = 2000) -> bytes:
    return struct.pack("<h", amplitude) * (16 * ms)


class Socket:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.sent: list[dict] = []
        self.closed = None

    async def receive(self) -> dict:
        await asyncio.sleep(0)
        return self.messages.pop(0) if self.messages else {"type": "websocket.disconnect"}

    async def send_json(self, value: dict) -> None:
        self.sent.append(value)

    async def close(self, code: int) -> None:
        self.closed = code


def msg(value: dict) -> dict:
    return {"type": "websocket.receive", "text": json.dumps(value)}


def start() -> dict:
    return msg({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})


def frame(seq: int, start_ms: int, end_ms: int, amplitude: int = 2000) -> list[dict]:
    return [msg({"type": "audio", "audioSeq": seq, "startMs": start_ms, "endMs": end_ms}),
            {"type": "websocket.receive", "bytes": pcm(end_ms - start_ms, amplitude)}]


def stream(socket: Socket, *, transcribe=None, decide=None, finalize=None, on_start=None) -> AudioStream:
    async def noop(*_):
        return None
    return AudioStream(meeting_id=str(uuid.uuid4()), websocket=socket, start=on_start or noop,
                       transcribe=transcribe or noop, decide=decide or noop,
                       finalize=finalize or noop, begin_finalizing=noop)


async def test_vad_suppresses_silence_and_short_click() -> None:
    vad = PcmVad()
    assert vad.feed(pcm(3000, 0) + pcm(40) + pcm(1000, 0)) == []
    assert vad.flush() is None


async def test_vad_preserves_pcm_across_arbitrary_frame_boundaries_and_flushes_tail() -> None:
    vad = PcmVad()
    audio = pcm(200, 0) + pcm(333)
    assert vad.feed(audio[:111]) == []
    assert vad.feed(audio[111:]) == []
    assert vad.flush() == Utterance(audio, 0, 533)


async def test_vad_endpoints_silence_and_caps_long_speech() -> None:
    vad = PcmVad()
    segments = vad.feed(pcm(800) + pcm(600, 0))
    assert len(segments) == 1
    assert (segments[0].start_ms, segments[0].end_ms) == (0, 1400)
    segments = vad.feed(pcm(16000))
    assert len(segments) == 1
    assert segments[0].end_ms - segments[0].start_ms == 15000
    assert vad.flush() is not None


async def test_end_flushes_tail_and_waits_for_ai_before_completed() -> None:
    socket = Socket([start(), *frame(1, 0, 300), msg({"type": "end", "lastAudioSeq": 1})])
    processed = []
    done = []
    async def transcribe(utterance):
        processed.append(utterance)
        return "segment-1"
    async def decide(segment_id):
        assert not any(event["type"] == "audio.completed" for event in socket.sent)
        await asyncio.sleep(0)
        done.append(segment_id)
    async def finalize(success):
        assert done == ["segment-1"]
        assert success
    audio = stream(socket, transcribe=transcribe, decide=decide, finalize=finalize)
    await audio.run()
    assert processed == [Utterance(pcm(300), 0, 300)]
    assert [event["type"] for event in socket.sent] == ["audio.ready", "audio.accepted", "audio.end_ack", "audio.completed"]
    assert socket.sent[-1]["status"] == "COMPLETED"
    assert socket.closed == 1000
    assert not is_recording(audio.meeting_id)


async def test_next_stt_and_receive_continue_while_previous_ai_waits() -> None:
    socket = Socket([start(), *frame(1, 0, 800), *frame(2, 800, 1400, 0),
                     *frame(3, 1400, 1800), msg({"type": "end", "lastAudioSeq": 3})])
    second_stt = asyncio.Event()
    count = 0
    async def transcribe(_):
        nonlocal count
        count += 1
        if count == 2:
            second_stt.set()
        return f"segment-{count}"
    async def decide(segment_id):
        if segment_id == "segment-1":
            await asyncio.wait_for(second_stt.wait(), timeout=1)
        assert any(event.get("audioSeq") == 3 for event in socket.sent)
    await stream(socket, transcribe=transcribe, decide=decide).run()
    assert count == 2
    assert socket.sent[-1]["status"] == "COMPLETED"


@pytest.mark.parametrize("invalid, code", [
    ([{"type": "websocket.receive", "bytes": pcm(100)}], "AUDIO_METADATA_REQUIRED"),
    ([msg({"type": "audio", "audioSeq": 2, "startMs": 0, "endMs": 100})], "AUDIO_SEQUENCE_GAP"),
    ([msg({"type": "audio", "audioSeq": 1, "startMs": 10, "endMs": 110})], "AUDIO_SEQUENCE_GAP"),
    ([msg({"type": "audio", "audioSeq": 1, "startMs": 0, "endMs": 100}), {"type": "websocket.receive", "bytes": pcm(50)}], "AUDIO_SIZE_MISMATCH"),
    ([msg({"type": "end", "lastAudioSeq": 1})], "AUDIO_END_MISMATCH"),
])
async def test_invalid_frames_fail_without_success(invalid, code) -> None:
    socket = Socket([start(), *invalid])
    audio = stream(socket)
    await audio.run()
    assert socket.sent[-1]["type"] == "audio.error"
    assert socket.sent[-1]["code"] == code
    assert socket.closed == 1008
    assert not is_recording(audio.meeting_id)


async def test_provider_failure_cannot_complete_successfully() -> None:
    socket = Socket([start(), *frame(1, 0, 300), msg({"type": "end", "lastAudioSeq": 1})])
    status = []
    async def transcribe(_):
        raise SttError("STT_TIMEOUT", "timeout")
    async def finalize(success):
        status.append(success)
    await stream(socket, transcribe=transcribe, finalize=finalize).run()
    assert status == [False]
    assert any(event.get("code") == "STT_TIMEOUT" for event in socket.sent)
    assert socket.sent[-1]["status"] == "FAILED"


async def test_stt_error_interval_uses_meeting_timeline() -> None:
    socket = Socket([start(), *frame(1, 0, 300), msg({"type": "end", "lastAudioSeq": 1})])

    async def start_with_offset():
        return 5000

    async def transcribe(_):
        raise SttError("STT_TIMEOUT", "timeout")

    await stream(socket, on_start=start_with_offset, transcribe=transcribe).run()
    error = next(event for event in socket.sent if event.get("code") == "STT_TIMEOUT")
    assert (error["startMs"], error["endMs"]) == (5000, 5300)
    assert socket.sent[-1]["status"] == "FAILED"


async def test_missing_config_releases_recorder_without_ready() -> None:
    socket = Socket([start()])
    async def missing():
        raise SttError("STT_NOT_CONFIGURED", "configure STT")
    audio = stream(socket, on_start=missing)
    await audio.run()
    assert socket.sent == [{"type": "audio.error", "code": "STT_NOT_CONFIGURED", "message": "configure STT"}]
    assert not is_recording(audio.meeting_id)


async def test_whisper_posts_wav_and_reads_nested_gateway_response() -> None:
    def respond(request):
        assert request.headers["Authorization"] == "Bearer private-test-key"
        assert b'filename="utterance.wav"' in request.content
        assert b'RIFF' in request.content
        assert b'\r\nko\r\n' in request.content
        return httpx.Response(200, json={"transcript": {"text": " 회의를 시작합니다. "}})
    provider = WhisperStt(url="https://gateway.example/transcriptions", api_key="private-test-key", transport=httpx.MockTransport(respond))
    assert await provider.transcribe(pcm_to_wav(pcm(300)), language="ko-KR") == "회의를 시작합니다."


async def test_whisper_failure_does_not_echo_body_or_key() -> None:
    provider = WhisperStt(url="https://gateway.example/transcriptions", api_key="private-test-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private-test-key secret transcript")))
    with pytest.raises(SttError) as error:
        await provider.transcribe(pcm_to_wav(pcm(300)), language="ko")
    assert error.value.code == "STT_PROVIDER_ERROR"
    assert "private-test-key" not in str(error.value)
    assert "secret transcript" not in str(error.value)


async def test_whisper_rejects_wrong_response() -> None:
    provider = WhisperStt(url="https://gateway.example/transcriptions", api_key="key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": "wrong shape"})))
    with pytest.raises(SttError) as error:
        await provider.transcribe(pcm_to_wav(pcm(300)), language="ko")
    assert error.value.code == "STT_INVALID_RESPONSE"


async def test_second_socket_cannot_replace_live_recorder() -> None:
    first = stream(Socket([]))
    await first._message(start())
    assert is_recording(first.meeting_id)
    second_socket = Socket([start()])
    second = stream(second_socket)
    second.meeting_id = first.meeting_id
    await second.run()
    assert second_socket.sent[-1]["code"] == "AUDIO_ALREADY_RECORDING"
    assert is_recording(first.meeting_id)
    await first.run()
    assert not is_recording(first.meeting_id)
