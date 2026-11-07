"""Single-server PCM stream framing and speech detection.

The receiver only validates frames and segments audio. One ordered worker performs
STT/persistence; each saved segment then gets its own AI task (capped), so a slow
judgment neither delays the next one nor stalls capture (#240).
"""

import asyncio
import json
import hashlib
import time
import math
import struct
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import webrtcvad
from fastapi import WebSocket, WebSocketDisconnect

from app.infra.stt import SttError

SAMPLE_RATE = 16000
BYTES_PER_MS = 32
MAX_FRAME_MS = 1000
RESUME_WINDOW_SECONDS = 60
RESUME_FRAME_LIMIT = 256


class AudioProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Utterance:
    pcm: bytes
    start_ms: int
    end_ms: int


class PcmVad:
    """20ms speech detection with 200ms pre-roll and 600ms silence endpointing.

    WebRTC VAD and an RMS floor reduce noise sent to STT; neither guarantees that
    every speech segment or every kind of noise is classified correctly.
    """

    def __init__(self, *, rms_threshold: float = 450) -> None:
        self.threshold = rms_threshold
        # The microphone is already noise-suppressed in the browser. Use the
        # stricter WebRTC mode for the remaining room/fan noise so it does not
        # become a Whisper hallucination.
        self.speech_detector = webrtcvad.Vad(3)
        self.pending = bytearray()
        self.offset_ms = 0
        self.pre_roll: deque[tuple[int, bytes]] = deque(maxlen=10)
        self.active: list[bytes] = []
        self.start_ms = 0
        self.voice_ms = 0
        self.silence_ms = 0

    def feed(self, pcm: bytes) -> list[Utterance]:
        self.pending.extend(pcm)
        result = []
        while len(self.pending) >= 640:
            block = bytes(self.pending[:640])
            del self.pending[:640]
            utterance = self._block(block)
            if utterance is not None:
                result.append(utterance)
        return result

    def _block(self, block: bytes) -> Utterance | None:
        duration = len(block) // BYTES_PER_MS
        samples = struct.unpack(f"<{len(block) // 2}h", block)
        mean = sum(samples) / len(samples)
        rms = math.sqrt(sum((sample - mean) ** 2 for sample in samples) / len(samples))
        # WebRTC requires a complete 10, 20, or 30ms frame, including the final tail.
        speech = self.speech_detector.is_speech(block.ljust(640, b"\0"), SAMPLE_RATE)
        voiced = rms >= self.threshold and speech
        block_start = self.offset_ms
        self.offset_ms += duration
        if not self.active:
            if not voiced:
                self.pre_roll.append((block_start, block))
                return None
            self.start_ms = self.pre_roll[0][0] if self.pre_roll else block_start
            self.active = [value for _, value in self.pre_roll]
            self.pre_roll.clear()
        self.active.append(block)
        self.voice_ms += duration if voiced else 0
        self.silence_ms = 0 if voiced else self.silence_ms + duration
        if self.silence_ms >= 600 or self.offset_ms - self.start_ms >= 15000:
            return self._take()
        return None

    def _take(self) -> Utterance | None:
        result = (
            Utterance(b"".join(self.active), self.start_ms, self.offset_ms)
            if self.voice_ms >= 160
            else None
        )
        self.active = []
        self.voice_ms = 0
        self.silence_ms = 0
        return result

    def flush(self) -> Utterance | None:
        result = None
        if self.pending:
            result = self._block(bytes(self.pending))
            self.pending.clear()
        return result or self._take()


# One producer per meeting; other authenticated sockets can still subscribe.
_recorders: set[str] = set()
# PCM stays bounded in the VAD tail; frame hashes permit safe ACK-loss replay.
_resume_states: dict[str, dict[str, Any]] = {}


def _forget_resume(meeting_id: str, state: dict[str, Any]) -> None:
    if _resume_states.get(meeting_id) is state:
        # Expiry must persist the accepted tail instead of silently dropping it.
        state["expires"] = 0
        asyncio.create_task(state["stream"]._expire_resume(state))


def is_recording(meeting_id: str) -> bool:
    return meeting_id in _recorders


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class AudioStream:
    def __init__(
        self,
        *,
        meeting_id: str,
        websocket: WebSocket,
        start: Callable[[], Awaitable[int | None]],
        resume: Callable[[], Awaitable[None]] | None = None,
        transcribe: Callable[[Utterance], Awaitable[str | None]],
        decide: Callable[[str], Awaitable[None]],
        finalize: Callable[[bool], Awaitable[None]],
        begin_finalizing: Callable[[], Awaitable[None]],
        rms_threshold: float = 450,
        ai_concurrency: int = 4,
    ) -> None:
        self.meeting_id = meeting_id
        self.ws = websocket
        self.on_start = start
        self.on_resume = resume
        self.frame_hashes: dict[int, tuple[int, int, str]] = {}
        self.resumed = False
        self.transcribe = transcribe
        self.decide = decide
        self.finalize = finalize
        self.begin_finalizing = begin_finalizing
        self.vad = PcmVad(rms_threshold=rms_threshold)
        self.audio_queue: asyncio.Queue[Utterance | None] = asyncio.Queue(maxsize=8)
        # 동시에 도는 AI 처리 수의 상한. 말이 몰려도 게이트웨이 호출이 한꺼번에 나가지 않게 한다.
        # 자리를 기다리는 처리는 ai_tasks 안에서 들어온 순서대로 기다리고, 전사는 막지 않는다.
        self.ai_slots = asyncio.Semaphore(ai_concurrency)
        self.ai_tasks: set[asyncio.Task] = set()
        self.audio_seq = 0
        self.end_ms = 0
        self.stream_offset_ms = 0
        self.failure = {"count": 0, "messages": deque(maxlen=16), "stream": self}
        self.previous: AudioStream | None = None
        self.finished = asyncio.Event()
        self.started = False
        self.connected = True
        self.pending_meta: dict[str, Any] | None = None
        self.tasks: list[asyncio.Task] = []

    @property
    def errors(self) -> int:
        return self.failure["count"]

    @errors.setter
    def errors(self, value: int) -> None:
        self.failure["count"] = value

    async def send(self, message: dict) -> None:
        if self.connected:
            try:
                await self.ws.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                self.connected = False

    async def error(self, code: str, message: str, **extra: Any) -> None:
        self.errors += 1
        event = {"type": "audio.error", "code": code, "message": message, **extra}
        self.failure["messages"].append(event)
        await self.failure["stream"].send(event)

    async def _audio_worker(self) -> None:
        # Resume handshakes stay fast; only STT waits for the preceding ordered worker.
        if self.previous and self.previous.tasks:
            await asyncio.shield(self.previous.tasks[0])
        while True:
            utterance = await self.audio_queue.get()
            try:
                if utterance is None:
                    return
                segment_id = await self.transcribe(utterance)
                if segment_id:
                    # 기다리지 않고 바로 다음 음성 구간으로 간다. 전사는 발화 순서대로 저장되므로
                    # 이 발화의 처리가 읽는 앞 발화(문맥)는 이미 DB에 있다.
                    self._start_decision(segment_id)
            except SttError as exc:
                await self.error(
                    exc.code, exc.message,
                    # Match transcript.final and audio.no_transcript's meeting timeline.
                    startMs=self.stream_offset_ms + utterance.start_ms,
                    endMs=self.stream_offset_ms + utterance.end_ms,
                )
            except Exception:
                await self.error("AUDIO_PROCESSING_FAILED", "음성 구간을 저장하거나 처리하지 못했습니다.")
            finally:
                self.audio_queue.task_done()

    def _start_decision(self, segment_id: str) -> None:
        task = asyncio.create_task(self._decide_one(segment_id))
        self.ai_tasks.add(task)
        task.add_done_callback(self.ai_tasks.discard)

    async def _decide_one(self, segment_id: str) -> None:
        # 앞 발화의 처리가 끝나기를 기다리지 않는다. 결과는 끝나는 대로 화면에 가므로
        # 발화 순서와 다르게 도착할 수 있고, 화면은 segmentId로 맞춘다(AI-MEET-06).
        async with self.ai_slots:
            try:
                await self.decide(segment_id)
            except Exception:
                await self.error(
                    "CONTEXT_PROCESSING_FAILED",
                    "전사는 저장했지만 자료 답·후보 처리에 실패했습니다.",
                    segmentId=segment_id,
                )

    def _enqueue(self, utterance: Utterance | None) -> None:
        if utterance is None:
            return
        try:
            self.audio_queue.put_nowait(utterance)
        except asyncio.QueueFull as exc:
            raise AudioProtocolError(
                "AUDIO_BACKPRESSURE",
                "음성 처리가 밀렸습니다. 녹음을 멈추고 저장된 전사를 확인해 주세요.",
            ) from exc

    async def _message(self, message: dict) -> bool:
        if message.get("bytes") is not None:
            if not self.started or self.pending_meta is None:
                raise AudioProtocolError("AUDIO_METADATA_REQUIRED", "오디오 메타데이터 다음에 binary 프레임을 보내 주세요.")
            meta = self.pending_meta
            pcm = message["bytes"]
            if len(pcm) % 2:
                raise AudioProtocolError("AUDIO_ODD_PCM", "PCM16 오디오는 2바이트 샘플 단위여야 합니다.")
            if len(pcm) != (meta["endMs"] - meta["startMs"]) * BYTES_PER_MS:
                raise AudioProtocolError("AUDIO_SIZE_MISMATCH", "PCM 길이가 startMs/endMs와 맞지 않습니다.")
            digest = hashlib.sha256(pcm).hexdigest()
            if meta["audioSeq"] <= self.audio_seq:
                if self.frame_hashes.get(meta["audioSeq"]) != (meta["startMs"], meta["endMs"], digest):
                    raise AudioProtocolError("AUDIO_REPLAY_MISMATCH", "재전송 프레임을 확인할 수 없습니다.")
                self.pending_meta = None
                await self.send({"type": "audio.accepted", "audioSeq": meta["audioSeq"]})
                return False
            self.frame_hashes[meta["audioSeq"]] = (meta["startMs"], meta["endMs"], digest)
            if len(self.frame_hashes) > RESUME_FRAME_LIMIT:
                del self.frame_hashes[min(self.frame_hashes)]
            for utterance in self.vad.feed(pcm):
                self._enqueue(utterance)
            self.audio_seq = meta["audioSeq"]
            self.end_ms = meta["endMs"]
            self.pending_meta = None
            await self.send({"type": "audio.accepted", "audioSeq": self.audio_seq})
            return False
        try:
            payload = json.loads(message.get("text") or "")
        except (ValueError, TypeError) as exc:
            raise AudioProtocolError("AUDIO_INVALID_JSON", "올바른 JSON 메시지를 보내 주세요.") from exc
        if not isinstance(payload, dict):
            raise AudioProtocolError("AUDIO_INVALID_JSON", "JSON 객체를 보내 주세요.")
        kind = payload.get("type")
        if kind in ("start", "resume"):
            if self.started or self.meeting_id in _recorders:
                raise AudioProtocolError("AUDIO_ALREADY_RECORDING", "이 회의는 이미 음성을 받고 있습니다.")
            if (
                payload.get("format") != "pcm_s16le"
                or not _integer(payload.get("sampleRate"))
                or payload.get("sampleRate") != SAMPLE_RATE
                or not _integer(payload.get("channels"))
                or payload.get("channels") != 1
            ):
                raise AudioProtocolError("AUDIO_UNSUPPORTED_FORMAT", "pcm_s16le, 16000Hz, mono만 지원합니다.")
            _recorders.add(self.meeting_id)
            try:
                if kind == "resume":
                    state = _resume_states.get(self.meeting_id)
                    last_ack = payload.get("lastAckSeq")
                    if (state is None or time.monotonic() >= state["expires"]
                            or not _integer(last_ack) or last_ack < max(0, state["audio_seq"] - RESUME_FRAME_LIMIT)
                            or last_ack > state["audio_seq"] or self.on_resume is None):
                        raise AudioProtocolError("AUDIO_RESUME_UNAVAILABLE", "복구 가능한 음성 구간이 없습니다. 저장된 전사를 확인해 주세요.")
                    await self.on_resume()
                    _resume_states.pop(self.meeting_id, None)
                    self.audio_seq, self.end_ms = state["audio_seq"], state["end_ms"]
                    self.stream_offset_ms, self.vad = state["offset"], state["vad"]
                    self.frame_hashes = state["hashes"]
                    self.previous = state["stream"]
                    self.failure = self.previous.failure
                    self.failure["stream"] = self
                    self.ai_slots = self.previous.ai_slots
                    self.resumed = True
                else:
                    if self.meeting_id in _resume_states:
                        raise AudioProtocolError("AUDIO_RESUME_REQUIRED", "기존 녹음을 재연결해 주세요.")
                    self.stream_offset_ms = (await self.on_start()) or 0
            except BaseException:
                _recorders.discard(self.meeting_id)
                raise
            self.started = True
            self.tasks = [asyncio.create_task(self._audio_worker())]
            await self.send({
                "type": "audio.ready", "format": "pcm_s16le",
                "sampleRate": SAMPLE_RATE, "channels": 1, "maxFrameMs": MAX_FRAME_MS,
                "streamOffsetMs": self.stream_offset_ms,
                **({"resumed": True, "lastAudioSeq": self.audio_seq, "endMs": self.end_ms} if kind == "resume" else {}),
            })
            if self.resumed:
                for event in self.failure["messages"]:
                    await self.send(event)
        elif kind == "audio":
            if not self.started or self.pending_meta is not None:
                raise AudioProtocolError("AUDIO_INVALID_ORDER", "start 후 메타데이터와 binary를 번갈아 보내 주세요.")
            seq, start, end = (payload.get(key) for key in ("audioSeq", "startMs", "endMs"))
            replay = self.resumed and _integer(seq) and seq <= self.audio_seq and seq in self.frame_hashes
            if (
                not all(_integer(value) for value in (seq, start, end))
                or (not replay and (seq != self.audio_seq + 1 or start != self.end_ms))
                or not 0 < end - start <= MAX_FRAME_MS
            ):
                raise AudioProtocolError("AUDIO_SEQUENCE_GAP", "audioSeq는 1부터 연속이며 시각은 0ms부터 이어져야 합니다.")
            self.pending_meta = payload
        elif kind == "end":
            if (
                not self.started or self.pending_meta is not None
                or not _integer(payload.get("lastAudioSeq"))
                or payload.get("lastAudioSeq") != self.audio_seq
            ):
                raise AudioProtocolError("AUDIO_END_MISMATCH", "마지막 binary 다음에 정확한 lastAudioSeq로 종료해 주세요.")
            self._enqueue(self.vad.flush())
            await self.begin_finalizing()
            await self.send({"type": "audio.end_ack", "lastAudioSeq": self.audio_seq, "status": "FINALIZING"})
            return True
        else:
            raise AudioProtocolError("AUDIO_UNKNOWN_MESSAGE", "지원하지 않는 메시지입니다.")
        return False

    async def _drain(self) -> None:
        # 회의 종료·연결 끊김 모두 남은 전사를 마치고, 그 뒤 진행 중인 AI 처리를 모두 끝낸다.
        # 전사 작업이 끝난 뒤에는 새 처리가 생기지 않으므로 이 시점의 ai_tasks가 전부다.
        if self.tasks:
            await self.audio_queue.put(None)
            await self.tasks[0]
            await asyncio.gather(*self.ai_tasks)
        if self.previous:
            await self.previous.finished.wait()

    async def _expire_resume(self, state: dict[str, Any]) -> None:
        await self.finished.wait()
        try:
            utterance = self.vad.flush()
            if utterance:
                segment_id = await self.transcribe(utterance)
                if segment_id:
                    await self._decide_one(segment_id)
        except Exception:
            await self.error("AUDIO_RESUME_EXPIRED", "재연결 시간이 지나 음성 복구를 마치지 못했습니다.")
        finally:
            try:
                # The recording ended without a complete client end handshake.
                await self.finalize(False)
            except Exception:
                await self.error("MEETING_FINALIZATION_FAILED", "회의 종료 상태를 저장하지 못했습니다.")
            if _resume_states.get(self.meeting_id) is state:
                _resume_states.pop(self.meeting_id, None)

    async def run(self) -> None:
        ended = False
        released = False
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    self.connected = False
                    break
                if await self._message(message):
                    ended = True
                    break
        except (AudioProtocolError, SttError) as exc:
            await self.error(exc.code, exc.message)
        except Exception:
            await self.error("AUDIO_STREAM_FAILED", "음성 연결을 처리하지 못했습니다. 저장된 전사를 확인해 주세요.")
        finally:
            try:
                # Keep already accepted utterances on disconnect/protocol failure.
                if self.started and not ended and self.connected:
                    try:
                        self._enqueue(self.vad.flush())
                    except AudioProtocolError:
                        self.errors += 1
                if self.started and not ended and not self.connected:
                    state = {"audio_seq": self.audio_seq, "end_ms": self.end_ms,
                             "offset": self.stream_offset_ms, "vad": self.vad,
                             "hashes": self.frame_hashes, "stream": self,
                             "expires": time.monotonic() + RESUME_WINDOW_SECONDS}
                    _resume_states[self.meeting_id] = state
                    asyncio.get_running_loop().call_later(RESUME_WINDOW_SECONDS, _forget_resume, self.meeting_id, state)
                    _recorders.discard(self.meeting_id)
                    released = True
                await self._drain()
                if ended:
                    try:
                        await self.finalize(self.errors == 0)
                        await self.send({
                            "type": "audio.completed", "lastAudioSeq": self.audio_seq,
                            "status": "COMPLETED" if self.errors == 0 else "FAILED",
                            "errorCount": self.errors,
                        })
                    except Exception:
                        await self.error("MEETING_FINALIZATION_FAILED", "음성 처리는 끝났지만 회의 종료 상태를 저장하지 못했습니다.")
                if self.connected:
                    await self.ws.close(code=1000 if ended else 1008)
            finally:
                if self.started and not released:
                    _recorders.discard(self.meeting_id)
                # 정상 흐름에서는 _drain이 모두 끝냈다. 서버 종료처럼 run 자체가 취소된 경우만 남는다.
                pending = [*self.tasks, *self.ai_tasks]
                for task in pending:
                    if not task.done():
                        task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                self.finished.set()
