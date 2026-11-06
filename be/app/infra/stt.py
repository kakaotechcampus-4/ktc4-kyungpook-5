"""Configured Whisper gateway adapter.

STT_URL is the complete transcription endpoint; it is deliberately separate from
chat/embedding deployments. The Whisper gateway returns ``transcript.text``;
some OpenAI-compatible gateways return top-level ``text``. No fallback
transcript is produced on provider errors.
"""

import io
import math
import struct
import wave

import httpx


# Whisper's no-speech score is meaningful only for verbose responses. Keep the
# threshold conservative so a real short utterance is not discarded.
NO_SPEECH_THRESHOLD = 0.6
MIN_AUDIO_RMS = 450.0
MIN_VOICED_MS = 160
LOGPROB_THRESHOLD = -1.0
COMPRESSION_RATIO_THRESHOLD = 2.4

# Some Whisper gateways echo this marker as ordinary transcript text. It is a
# gap, not something a meeting participant said, so it must not become a row.
UNRECOGNIZED_TRANSCRIPT_MARKERS = frozenset(
    {"알아듣지 못했어요", "(알아듣지 못했어요)"}
)


class SttError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def pcm_to_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue()


class WhisperStt:
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        model: str = "openai/whisper-large-v3",
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not url.strip() or not api_key.strip():
            raise SttError("STT_NOT_CONFIGURED", "STT_URL과 STT_API_KEY를 설정해 주세요.")
        self.url = url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def transcribe(self, wav: bytes, *, language: str) -> str:
        # Some MLAPI Whisper deployments return HTTP 200 with a canned phrase
        # for an entirely silent WAV and ignore no_speech/temperature options.
        # The VAD uses the same floor, so reject a chunk with no voiced-energy
        # before it can become a fake transcript.
        if not _contains_voiced_energy(wav):
            return ""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                request = {
                    "headers": {"Authorization": f"Bearer {self.api_key}"},
                    "files": {"file": ("utterance.wav", wav, "audio/wav")},
                }
                response = await client.post(
                    self.url,
                    **request,
                    data={
                        "model": self.model,
                        "language": language.split("-")[0],
                        "response_format": "verbose_json",
                        "temperature": "0",
                        "condition_on_previous_text": "false",
                        "no_speech_threshold": str(NO_SPEECH_THRESHOLD),
                        "logprob_threshold": str(LOGPROB_THRESHOLD),
                        "compression_ratio_threshold": str(COMPRESSION_RATIO_THRESHOLD),
                    },
                )
                if response.status_code in (400, 422):
                    # Older MLAPI Whisper deployments accept only model/language.
                    # Retry the same audio without optional controls so a gateway
                    # upgrade does not turn every utterance into a provider error.
                    response = await client.post(
                        self.url,
                        **request,
                        data={"model": self.model, "language": language.split("-")[0]},
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise TypeError("response must be an object")
                transcript = payload.get("transcript")
                if isinstance(transcript, dict):
                    text = transcript.get("text")
                    segments = transcript.get("segments")
                else:
                    text = payload.get("text")
                    segments = payload.get("segments")
                if not isinstance(text, str):
                    raise TypeError("transcript.text or text must be a string")
                if _is_silence_response(payload, segments):
                    return ""
                if _is_low_confidence_response(segments):
                    return ""
                normalized_text = " ".join(text.split())
                if normalized_text in UNRECOGNIZED_TRANSCRIPT_MARKERS:
                    return ""
                if _is_repeated_short_phrase(normalized_text):
                    return ""
                return normalized_text
        except httpx.TimeoutException as exc:
            raise SttError("STT_TIMEOUT", "음성 인식 응답 시간이 초과됐습니다.") from exc
        except httpx.HTTPError as exc:
            # Provider response bodies can contain private audio/transcripts or tokens.
            raise SttError("STT_PROVIDER_ERROR", "음성 인식 서비스 호출에 실패했습니다.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise SttError("STT_INVALID_RESPONSE", "음성 인식 응답 형식이 올바르지 않습니다.") from exc


def _contains_voiced_energy(wav: bytes) -> bool:
    """Return whether a 16-bit mono WAV contains sustained voiced energy."""
    try:
        with wave.open(io.BytesIO(wav), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                return True
            pcm = source.readframes(source.getnframes())
    except (EOFError, wave.Error):
        return True
    if not pcm:
        return False
    voiced_ms = 0
    for offset in range(0, len(pcm), 640):
        block = pcm[offset : offset + 640]
        if len(block) < 2:
            continue
        samples = struct.unpack(f"<{len(block) // 2}h", block[: len(block) - len(block) % 2])
        mean = sum(samples) / len(samples)
        rms = math.sqrt(sum((sample - mean) ** 2 for sample in samples) / len(samples))
        if rms >= MIN_AUDIO_RMS:
            voiced_ms += len(block) // 2 // 16
            if voiced_ms >= MIN_VOICED_MS:
                return True
        else:
            # A single noisy frame is enough to trigger the old gate and make
            # Whisper invent a canned phrase. Require one short, continuous
            # voiced run before sending audio to the provider.
            voiced_ms = 0
    return False


def _is_repeated_short_phrase(text: str) -> bool:
    """Reject a short phrase repeated verbatim by a silence hallucination."""
    tokens = text.split()
    if len(tokens) < 2 or len(text) > 48:
        return False
    for repeats in (2, 3, 4):
        if len(tokens) % repeats:
            continue
        unit_size = len(tokens) // repeats
        if unit_size > 4:
            continue
        unit = tokens[:unit_size]
        # Keep natural short acknowledgements such as "네 네"; canned Whisper
        # phrases are long enough to be safely identified by their token text.
        if len(" ".join(unit)) < 3:
            continue
        if all(
            tokens[index : index + unit_size] == unit
            for index in range(0, len(tokens), unit_size)
        ):
            return True
    return False


def _is_silence_response(payload: dict, segments: object) -> bool:
    """Return true only when the provider explicitly marks the audio as silence.

    Some gateways wrap the OpenAI verbose response under ``transcript`` while
    others return it at the top level. Missing metadata is accepted for
    backwards compatibility with the text-only gateway response.
    """
    no_speech = payload.get("no_speech_prob")
    if isinstance(payload.get("transcript"), dict):
        no_speech = payload["transcript"].get("no_speech_prob", no_speech)
    if no_speech is not None and (
        isinstance(no_speech, bool) or not isinstance(no_speech, (int, float))
    ):
        raise ValueError("no_speech_prob must be numeric")
    if isinstance(no_speech, (int, float)) and not isinstance(no_speech, bool):
        if no_speech >= NO_SPEECH_THRESHOLD:
            return True

    if not isinstance(segments, list) or not segments:
        return False
    probabilities: list[float] = []
    for segment in segments:
        if not isinstance(segment, dict) or "no_speech_prob" not in segment:
            return False
        value = segment.get("no_speech_prob")
        # MLAPI returns null for this field even in a valid verbose response.
        # Missing probability means we cannot classify the response as silence.
        if value is None:
            return False
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("segment.no_speech_prob must be numeric")
        probabilities.append(float(value))
    return bool(probabilities) and all(value >= NO_SPEECH_THRESHOLD for value in probabilities)


def _is_low_confidence_response(segments: object) -> bool:
    """Return true for a response whose verbose segments are likely hallucinated."""
    if not isinstance(segments, list) or not segments:
        return False

    avg_logprobs: list[float] = []
    compression_ratios: list[float] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        avg_logprob = segment.get("avg_logprob")
        if avg_logprob is not None:
            if isinstance(avg_logprob, bool) or not isinstance(avg_logprob, (int, float)):
                raise ValueError("segment.avg_logprob must be numeric")
            avg_logprobs.append(float(avg_logprob))
        compression_ratio = segment.get("compression_ratio")
        if compression_ratio is not None:
            if isinstance(compression_ratio, bool) or not isinstance(compression_ratio, (int, float)):
                raise ValueError("segment.compression_ratio must be numeric")
            compression_ratios.append(float(compression_ratio))

    if avg_logprobs and sum(avg_logprobs) / len(avg_logprobs) < LOGPROB_THRESHOLD:
        return True
    return bool(compression_ratios) and any(
        value > COMPRESSION_RATIO_THRESHOLD for value in compression_ratios
    )
