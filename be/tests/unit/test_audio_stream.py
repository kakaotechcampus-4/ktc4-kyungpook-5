"""PCM/VAD, end-tail drain, provider failures and independent STT/AI execution."""

import asyncio
import json
import math
import random
import struct
import uuid

import httpx
import pytest

from app.infra.stt import SttError, WhisperStt, pcm_to_wav
from app.services.audio_stream_service import AudioStream, PcmVad, Utterance, is_recording

pytestmark = pytest.mark.anyio


def pcm(ms: int, amplitude: int = 2000) -> bytes:
    samples = [int(amplitude * math.sin(2 * math.pi * 200 * i / 16000)) for i in range(16 * ms)]
    return struct.pack(f"<{len(samples)}h", *samples)


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


async def test_vad_suppresses_stationary_noise_above_energy_threshold() -> None:
    rng = random.Random(42)
    samples = [rng.randint(-1800, 1800) for _ in range(16000 * 4)]
    noise = struct.pack(f"<{len(samples)}h", *samples)
    vad = PcmVad()
    assert vad.feed(noise) == []
    assert vad.flush() is None


async def test_vad_suppresses_low_level_noise_and_preserves_short_voiced_tail() -> None:
    rng = random.Random(11)
    samples = [rng.randint(-300, 300) for _ in range(16000)]
    noise = struct.pack(f"<{len(samples)}h", *samples)
    vad = PcmVad()
    assert vad.feed(noise) == []
    assert vad.flush() is None

    vad = PcmVad()
    assert vad.feed(pcm(160)) == []
    assert vad.flush() == Utterance(pcm(160), 0, 160)

async def test_stream_rejects_odd_pcm16_payload_before_vad() -> None:
    socket = Socket([start(), msg({"type": "audio", "audioSeq": 1, "startMs": 0, "endMs": 1}),
                         {"type": "websocket.receive", "bytes": b"\x00"}])
    audio = stream(socket)
    await audio.run()
    assert any(event.get("code") == "AUDIO_ODD_PCM" for event in socket.sent)


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


def utterances(count: int) -> list[dict]:
    """발화 count개: 말 300ms + 침묵 600ms를 한 쌍으로 보내 VAD가 발화 하나로 자른다."""
    messages = []
    for index in range(count):
        base = index * 900
        messages += frame(2 * index + 1, base, base + 300)
        messages += frame(2 * index + 2, base + 300, base + 900, 0)
    return messages


def ended(count: int) -> list[dict]:
    return [start(), *utterances(count), msg({"type": "end", "lastAudioSeq": 2 * count})]


def numbered_transcribe():
    count = 0
    async def transcribe(_):
        nonlocal count
        count += 1
        return f"segment-{count}"
    return transcribe


async def test_next_decision_starts_without_waiting_for_previous_one() -> None:
    # #240: 앞 발화의 판단이 끝나지 않아도 다음 발화의 판단이 바로 시작돼야 한다.
    # segment-1은 segment-2가 끝날 때까지 멈춰 있으므로, 하나씩 처리하면 끝나지 못한다.
    socket = Socket(ended(2))
    second_done = asyncio.Event()
    done = []
    async def decide(segment_id):
        if segment_id == "segment-1":
            await asyncio.wait_for(second_done.wait(), timeout=1)
        done.append(segment_id)
        if segment_id == "segment-2":
            second_done.set()
    at_finalize = []
    async def finalize(success):
        at_finalize.append((list(done), success))
    await asyncio.wait_for(
        stream(socket, transcribe=numbered_transcribe(), decide=decide, finalize=finalize).run(),
        timeout=5,
    )
    # 둘째 결과가 먼저 오고, 회의 종료는 진행 중인 판단을 모두 마친 뒤에 한다.
    assert at_finalize == [(["segment-2", "segment-1"], True)]
    assert socket.sent[-1]["status"] == "COMPLETED"


async def test_ai_backlog_does_not_stop_stt_or_cause_backpressure() -> None:
    # #240: 판단이 모두 밀려 있어도 전사는 계속되고 AUDIO_BACKPRESSURE로 회의가 끊기지 않는다.
    # 30개는 기존 큐 두 개(AI 16, 음성 8)를 합친 것보다 많다.
    total = 30
    socket = Socket(ended(total))
    transcribed = 0
    all_transcribed = asyncio.Event()
    decided = []
    async def transcribe(_):
        nonlocal transcribed
        transcribed += 1
        if transcribed == total:
            all_transcribed.set()
        return f"segment-{transcribed}"
    async def decide(segment_id):
        # 전사가 모두 끝날 때까지 어떤 판단도 끝나지 않는다.
        # 백프레셔가 나면 바로 풀어서, 하나씩 시간 초과를 기다리지 않고 아래 assert로 실패하게 한다.
        while not all_transcribed.is_set() and not backpressure():
            await asyncio.sleep(0.01)
        decided.append(segment_id)
    def backpressure():
        return any(event.get("code") == "AUDIO_BACKPRESSURE" for event in socket.sent)
    await asyncio.wait_for(stream(socket, transcribe=transcribe, decide=decide).run(), timeout=10)
    assert not backpressure()
    assert transcribed == total
    assert sorted(decided) == sorted(f"segment-{i}" for i in range(1, total + 1))
    assert socket.sent[-1]["status"] == "COMPLETED"


async def test_concurrent_decisions_are_capped() -> None:
    # #240: 말이 몰려도 게이트웨이 호출이 한꺼번에 나가지 않게 동시에 도는 판단을 4개로 막는다.
    total = 10
    socket = Socket(ended(total))
    transcribed = 0
    running = 0
    peak = 0
    async def transcribe(_):
        nonlocal transcribed
        transcribed += 1
        return f"segment-{transcribed}"
    async def decide(_):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        # 10개가 모두 전사될 때까지 붙잡아 둬서, 상한이 없다면 10개가 동시에 돌게 한다.
        while transcribed < total:
            await asyncio.sleep(0.01)
        running -= 1
    await asyncio.wait_for(stream(socket, transcribe=transcribe, decide=decide).run(), timeout=5)
    assert peak == 4
    assert socket.sent[-1]["status"] == "COMPLETED"


async def test_disconnect_still_finishes_running_decisions() -> None:
    # #240: 연결이 끊겨도 진행 중인 판단은 끝까지 해서 판단 기록에 저장한다.
    socket = Socket([start(), *utterances(3)])  # end 없이 끊김
    done = []
    async def decide(segment_id):
        await asyncio.sleep(0.01)
        done.append(segment_id)
    await asyncio.wait_for(
        stream(socket, transcribe=numbered_transcribe(), decide=decide).run(), timeout=5,
    )
    assert sorted(done) == ["segment-1", "segment-2", "segment-3"]


@pytest.mark.parametrize("invalid, code", [
    ([{"type": "websocket.receive", "bytes": pcm(100)}], "AUDIO_METADATA_REQUIRED"),
    ([msg({"type": "audio", "audioSeq": 2, "startMs": 0, "endMs": 100})], "AUDIO_SEQUENCE_GAP"),
    ([*frame(1, 0, 100), msg({"type": "audio", "audioSeq": 1, "startMs": 100, "endMs": 200})], "AUDIO_SEQUENCE_GAP"),
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
        assert b'\r\nopenai/whisper-large-v3\r\n' in request.content
        return httpx.Response(200, json={"transcript": {"text": " 회의를 시작합니다. "}})
    provider = WhisperStt(url="https://gateway.example/transcriptions", api_key="private-test-key", transport=httpx.MockTransport(respond))
    assert await provider.transcribe(pcm_to_wav(pcm(300)), language="ko-KR") == "회의를 시작합니다."


async def test_whisper_reads_openai_compatible_response() -> None:
    provider = WhisperStt(
        url="https://mlapi.run/v1/audio/transcriptions",
        api_key="private-test-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": " 회의 기록 "})),
    )
    assert await provider.transcribe(pcm_to_wav(pcm(300)), language="ko") == "회의 기록"


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
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": {"text": "wrong shape"}})))
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


async def test_resume_replays_ack_lost_frame_once_and_keeps_tail():
    meeting_id = str(uuid.uuid4())
    saved = []
    async def noop(*_): return None
    async def transcribe(utterance): saved.append(utterance); return None
    first = Socket([start(), *frame(1, 0, 100)])
    await AudioStream(meeting_id=meeting_id, websocket=first, start=noop, resume=noop,
        transcribe=transcribe, decide=noop, finalize=noop, begin_finalizing=noop).run()
    assert saved == []
    resume = msg({'type':'resume', 'format':'pcm_s16le', 'sampleRate':16000, 'channels':1, 'lastAckSeq':0})
    second = Socket([resume, *frame(1, 0, 100), *frame(2, 100, 300), msg({'type':'end','lastAudioSeq':2})])
    await AudioStream(meeting_id=meeting_id, websocket=second, start=noop, resume=noop,
        transcribe=transcribe, decide=noop, finalize=noop, begin_finalizing=noop).run()
    ready = second.sent[0]
    assert ready['resumed'] and ready['lastAudioSeq'] == 1 and ready['endMs'] == 100
    assert len(saved) == 1 and saved[0].start_ms == 0 and saved[0].end_ms == 300
    assert saved[0].pcm == pcm(100) + pcm(200)
    assert second.sent[-1]['status'] == 'COMPLETED'


async def test_resume_rejects_unknown_state_and_replay_mismatch():
    async def noop(*_): return None
    meeting_id = str(uuid.uuid4())
    resume = msg({'type':'resume', 'format':'pcm_s16le', 'sampleRate':16000, 'channels':1, 'lastAckSeq':0})
    missing = Socket([resume])
    await AudioStream(meeting_id=meeting_id, websocket=missing, start=noop, resume=noop,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    assert missing.sent[-1]['code'] == 'AUDIO_RESUME_UNAVAILABLE'
    first = Socket([start(), *frame(1,0,100)])
    await AudioStream(meeting_id=meeting_id, websocket=first, start=noop, resume=noop,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    bad = Socket([resume, *frame(1,0,100, amplitude=3000)])
    await AudioStream(meeting_id=meeting_id, websocket=bad, start=noop, resume=noop,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    assert bad.sent[-1]['code'] == 'AUDIO_REPLAY_MISMATCH' and bad.closed == 1008


async def test_resume_permission_failure_leaves_recoverable_state():
    from app.services.audio_stream_service import AudioProtocolError
    async def noop(*_): return None
    async def forbidden(): raise AudioProtocolError('AUDIO_FORBIDDEN', '권한 없음')
    meeting_id = str(uuid.uuid4())
    first = Socket([start(), *frame(1,0,100)])
    await AudioStream(meeting_id=meeting_id, websocket=first, start=noop, resume=noop,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    handshake = msg({'type':'resume','format':'pcm_s16le','sampleRate':16000,'channels':1,'lastAckSeq':1})
    denied = Socket([handshake])
    await AudioStream(meeting_id=meeting_id, websocket=denied, start=noop, resume=forbidden,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    assert denied.sent[-1]['code'] == 'AUDIO_FORBIDDEN'
    allowed = Socket([handshake, msg({'type':'end','lastAudioSeq':1})])
    await AudioStream(meeting_id=meeting_id, websocket=allowed, start=noop, resume=noop,
        transcribe=noop, decide=noop, finalize=noop, begin_finalizing=noop).run()
    assert allowed.sent[0]['resumed'] and allowed.sent[-1]['status'] == 'COMPLETED'
