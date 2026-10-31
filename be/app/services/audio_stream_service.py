"""Single-server PCM stream framing and energy VAD.

The receiver only validates frames and segments audio. Bounded, ordered workers
perform STT/persistence and AI independently, so model latency does not stall capture.
"""

import asyncio
import json
import math
import struct
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.infra.stt import SttError

SAMPLE_RATE = 16000
BYTES_PER_MS = 32
MAX_FRAME_MS = 1000


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
    """20ms RMS VAD with 200ms pre-roll and 600ms silence endpointing.

    This deterministic first beta detector suppresses silence; loud background noise
    may still count as speech. A 15s maximum keeps requests and memory bounded.
    """

    def __init__(self, *, rms_threshold: float = 450) -> None:
        self.threshold = rms_threshold
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
        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        voiced = rms >= self.threshold
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
        transcribe: Callable[[Utterance], Awaitable[str | None]],
        decide: Callable[[str], Awaitable[None]],
        finalize: Callable[[bool], Awaitable[None]],
        begin_finalizing: Callable[[], Awaitable[None]],
        rms_threshold: float = 450,
    ) -> None:
        self.meeting_id = meeting_id
        self.ws = websocket
        self.on_start = start
        self.transcribe = transcribe
        self.decide = decide
        self.finalize = finalize
        self.begin_finalizing = begin_finalizing
        self.vad = PcmVad(rms_threshold=rms_threshold)
        self.audio_queue: asyncio.Queue[Utterance | None] = asyncio.Queue(maxsize=8)
        self.ai_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=16)
        self.audio_seq = 0
        self.end_ms = 0
        self.stream_offset_ms = 0
        self.errors = 0
        self.started = False
        self.connected = True
        self.pending_meta: dict[str, Any] | None = None
        self.tasks: list[asyncio.Task] = []

    async def send(self, message: dict) -> None:
        if self.connected:
            try:
                await self.ws.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                self.connected = False

    async def error(self, code: str, message: str, **extra: Any) -> None:
        self.errors += 1
        await self.send({"type": "audio.error", "code": code, "message": message, **extra})

    async def _audio_worker(self) -> None:
        while True:
            utterance = await self.audio_queue.get()
            try:
                if utterance is None:
                    return
                segment_id = await self.transcribe(utterance)
                if segment_id:
                    await self.ai_queue.put(segment_id)
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

    async def _ai_worker(self) -> None:
        while True:
            segment_id = await self.ai_queue.get()
            try:
                if segment_id is None:
                    return
                await self.decide(segment_id)
            except Exception:
                await self.error(
                    "CONTEXT_PROCESSING_FAILED",
                    "전사는 저장했지만 자료 답·후보 처리에 실패했습니다.",
                    segmentId=segment_id,
                )
            finally:
                self.ai_queue.task_done()

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
            if len(pcm) != (meta["endMs"] - meta["startMs"]) * BYTES_PER_MS:
                raise AudioProtocolError("AUDIO_SIZE_MISMATCH", "PCM 길이가 startMs/endMs와 맞지 않습니다.")
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
        if kind == "start":
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
                self.stream_offset_ms = (await self.on_start()) or 0
            except BaseException:
                _recorders.discard(self.meeting_id)
                raise
            self.started = True
            self.tasks = [
                asyncio.create_task(self._audio_worker()),
                asyncio.create_task(self._ai_worker()),
            ]
            await self.send({
                "type": "audio.ready", "format": "pcm_s16le",
                "sampleRate": SAMPLE_RATE, "channels": 1, "maxFrameMs": MAX_FRAME_MS,
                "streamOffsetMs": self.stream_offset_ms,
            })
        elif kind == "audio":
            if not self.started or self.pending_meta is not None:
                raise AudioProtocolError("AUDIO_INVALID_ORDER", "start 후 메타데이터와 binary를 번갈아 보내 주세요.")
            seq, start, end = (payload.get(key) for key in ("audioSeq", "startMs", "endMs"))
            if (
                not all(_integer(value) for value in (seq, start, end))
                or seq != self.audio_seq + 1
                or start != self.end_ms
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
        if self.tasks:
            await self.audio_queue.put(None)
            await self.tasks[0]
            await self.ai_queue.put(None)
            await self.tasks[1]

    async def run(self) -> None:
        ended = False
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
                if self.started and not ended:
                    try:
                        self._enqueue(self.vad.flush())
                    except AudioProtocolError:
                        self.errors += 1
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
                if self.started:
                    _recorders.discard(self.meeting_id)
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
                if self.tasks:
                    await asyncio.gather(*self.tasks, return_exceptions=True)
