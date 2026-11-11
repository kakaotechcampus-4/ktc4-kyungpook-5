import asyncio
import io
import json
import wave

import httpx
import pytest

from app.infra.diarization import DiarizationError, PyannoteDiarization


def _wav(duration_ms: int = 100) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x01\x00" * (duration_ms * 16))
    return output.getvalue()


def test_submit_uploads_without_forwarding_bearer_and_returns_job(tmp_path):
    path = tmp_path / "meeting.wav"
    path.write_bytes(_wav())
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.headers.get("authorization")))
        if request.url.path.endswith("/media/input"):
            return httpx.Response(200, json={"url": "https://signed.example/upload"})
        if request.url.host == "signed.example":
            assert request.content == path.read_bytes()
            assert request.headers.get("authorization") is None
            return httpx.Response(200)
        if request.url.path.endswith("/diarize"):
            return httpx.Response(200, json={"jobId": "job_1"})
        raise AssertionError(request.url)

    result = asyncio.run(PyannoteDiarization("secret", transport=httpx.MockTransport(handler)).submit(path))
    assert result == "job_1"
    assert seen[0][2] == "Bearer secret" and seen[1][2] is None


def test_result_normalizes_turns_and_keeps_overlap():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "jobId": "job_1", "status": "succeeded",
            "output": {"diarization": [
                {"start": 0.11, "end": 0.2, "speaker": "SPEAKER_02"},
                {"start": 0.1, "end": 0.15, "speaker": "SPEAKER_01"},
            ]},
        })

    turns = asyncio.run(PyannoteDiarization("secret", transport=httpx.MockTransport(handler)).result("job_1", duration_ms=200))
    assert turns == [
        {"start_ms": 100, "end_ms": 150, "speaker_label": "SPEAKER_01"},
        {"start_ms": 110, "end_ms": 200, "speaker_label": "SPEAKER_02"},
    ]


@pytest.mark.parametrize("url", ["http://signed.example/upload", "https://user@signed.example/upload", "https://[bad/upload"])
def test_submit_rejects_non_private_or_malformed_signed_url(tmp_path, url):
    path = tmp_path / "meeting.wav"
    path.write_bytes(_wav())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": url})

    with pytest.raises(DiarizationError) as error:
        asyncio.run(PyannoteDiarization("secret", transport=httpx.MockTransport(handler)).submit(path))
    assert error.value.code == "DIARIZATION_INVALID_RESPONSE"


def test_pending_job_must_match_when_provider_echoes_another_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobId": "other", "status": "running"})

    with pytest.raises(DiarizationError, match="작업 정보를"):
        asyncio.run(PyannoteDiarization("secret", transport=httpx.MockTransport(handler)).result("job_1", duration_ms=100))


def test_provider_error_is_safe_and_does_not_include_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=json.dumps({"secret_audio": "private"}))

    with pytest.raises(DiarizationError) as error:
        asyncio.run(PyannoteDiarization("secret", transport=httpx.MockTransport(handler)).result("job_1", duration_ms=100))
    assert error.value.code == "DIARIZATION_PROVIDER_ERROR"
    assert "private" not in str(error.value)
