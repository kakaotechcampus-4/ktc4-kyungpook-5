"""Configured Whisper gateway adapter. The gateway returns transcript.text.

STT_URL is the complete transcription endpoint; it is deliberately separate from
chat/embedding deployments. No fallback transcript is produced on provider errors.
"""

import io
import wave

import httpx


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
        model: str = "whisper-large-v3",
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
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files={"file": ("utterance.wav", wav, "audio/wav")},
                    data={"model": self.model, "language": language.split("-")[0]},
                )
                response.raise_for_status()
                payload = response.json()
                text = payload["transcript"]["text"]
                if not isinstance(text, str):
                    raise TypeError("transcript.text must be a string")
                return text.strip()
        except httpx.TimeoutException as exc:
            raise SttError("STT_TIMEOUT", "음성 인식 응답 시간이 초과됐습니다.") from exc
        except httpx.HTTPError as exc:
            # Provider response bodies can contain private audio/transcripts or tokens.
            raise SttError("STT_PROVIDER_ERROR", "음성 인식 서비스 호출에 실패했습니다.") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise SttError("STT_INVALID_RESPONSE", "음성 인식 응답 형식이 올바르지 않습니다.") from exc
