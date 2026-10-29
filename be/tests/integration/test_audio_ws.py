"""Real WS+DB persistence, with only external STT and AI work replaced in tests."""

import struct
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db import session as db_session
from app.infra.stt import SttError, WhisperStt
from app.routers import meetings as meetings_router
from app.services import meeting_service
from app.models.meetings import MeetingAudioChunk

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def audio_db(migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None, tmp_path) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("STT_URL", "https://gateway.example/transcriptions")
    monkeypatch.setenv("STT_API_KEY", "fake-key-for-test")
    get_settings.cache_clear()
    yield
    await db_session.get_engine().dispose()


def account_meeting(client: TestClient, *, consent: bool = True) -> tuple[str, str]:
    email = f"audio-{uuid.uuid4().hex[:12]}@example.com"
    assert client.post("/api/v1/auth/signup", json={"email": email, "password": "AudioTest-2027!", "name": "Audio tester"}).status_code == 201
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "AudioTest-2027!"}).json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {token}"}
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "Audio club"}).json()["data"]["id"]
    created = client.post(f"/api/v1/clubs/{club}/meetings", headers=headers, json={"recordingConsentConfirmed": consent}).json()["data"]
    assert created["clubId"] == club
    meeting = created["id"]
    assert client.get(f"/api/v1/meetings/{meeting}", headers=headers).json()["data"]["clubId"] == club
    return token, meeting


async def test_ws_tail_is_committed_before_context_failure(client: TestClient, audio_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def transcribe(self, wav: bytes, *, language: str) -> str:
        assert wav[:4] == b"RIFF"
        assert language == "ko-KR"
        return "다음 주 금요일까지 민수가 자료를 정리해 주세요."

    async def context_failure(*_, **__) -> None:
        raise RuntimeError("External model unavailable in this persistence test")

    monkeypatch.setattr(WhisperStt, "transcribe", transcribe)
    monkeypatch.setattr(meeting_service, "process_saved_segment", context_failure)
    token, meeting = account_meeting(client)
    headers = {"Authorization": f"Bearer {token}"}
    started = client.get(f"/api/v1/meetings/{meeting}", headers=headers).json()["data"]["startedAt"]
    received_at = datetime.fromisoformat(started.replace("Z", "+00:00")) + timedelta(seconds=5)
    monkeypatch.setattr(meetings_router, "datetime", SimpleNamespace(now=lambda _: received_at))
    with client.websocket_connect(f"/api/v1/meetings/{meeting}/stream?token={token}") as ws:
        ws.send_json({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})
        ready = ws.receive_json()
        assert ready["type"] == "audio.ready"
        # The API serializer exposes whole seconds while DB keeps microseconds.
        offset = ready["streamOffsetMs"]
        assert 4000 <= offset <= 5000
        # Metadata remains stream-relative. Stored evidence uses meeting time.
        # 300ms voiced tail with no trailing silence must survive end.
        ws.send_json({"type": "audio", "audioSeq": 1, "startMs": 0, "endMs": 300})
        ws.send_bytes(struct.pack("<h", 2000) * 4800)
        assert ws.receive_json()["type"] == "audio.accepted"
        ws.send_json({"type": "end", "lastAudioSeq": 1})
        events = []
        for _ in range(20):
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "audio.completed":
                break
        transcript = next(event for event in events if event["type"] == "transcript.final")
        assert transcript["text"] == "다음 주 금요일까지 민수가 자료를 정리해 주세요."
        assert transcript["startMs"] == offset and transcript["endMs"] == offset + 300
        assert transcript["decisionJobId"] is None
        assert any(event.get("code") == "CONTEXT_PROCESSING_FAILED" for event in events)
        assert events[-1]["status"] == "FAILED"
    headers = {"Authorization": f"Bearer {token}"}
    saved = client.get(f"/api/v1/meetings/{meeting}/transcripts", headers=headers).json()["data"]
    assert saved["cursor"] == 1
    assert saved["items"][0]["text"] == transcript["text"]
    async with db_session.get_sessionmaker()() as session:
        chunk = await session.scalar(select(MeetingAudioChunk).where(MeetingAudioChunk.meeting_id == meeting))
        assert chunk.storage_key is None and chunk.size > 0
    assert saved["items"][0]["startMs"] == offset
    assert saved["items"][0]["endMs"] == offset + 300
    assert client.get(f"/api/v1/meetings/{meeting}", headers=headers).json()["data"]["status"] == "FAILED"


async def test_ws_provider_error_does_not_create_fake_transcript(client: TestClient, audio_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(*_, **__) -> str:
        raise SttError("STT_PROVIDER_ERROR", "provider unavailable")

    monkeypatch.setattr(WhisperStt, "transcribe", unavailable)
    token, meeting = account_meeting(client)
    headers = {"Authorization": f"Bearer {token}"}
    started = client.get(f"/api/v1/meetings/{meeting}", headers=headers).json()["data"]["startedAt"]
    received_at = datetime.fromisoformat(started.replace("Z", "+00:00")) + timedelta(seconds=5)
    monkeypatch.setattr(meetings_router, "datetime", SimpleNamespace(now=lambda _: received_at))
    with client.websocket_connect(f"/api/v1/meetings/{meeting}/stream?token={token}") as ws:
        ws.send_json({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})
        ready = ws.receive_json()
        assert ready["type"] == "audio.ready" and ready["streamOffsetMs"] >= 4000
        ws.send_json({"type": "audio", "audioSeq": 1, "startMs": 0, "endMs": 300})
        ws.send_bytes(struct.pack("<h", 2000) * 4800)
        assert ws.receive_json()["type"] == "audio.accepted"
        ws.send_json({"type": "end", "lastAudioSeq": 1})
        events = []
        for _ in range(20):
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "audio.completed":
                break
        error = next(event for event in events if event.get("code") == "STT_PROVIDER_ERROR")
        assert (error["startMs"], error["endMs"]) == (
            ready["streamOffsetMs"], ready["streamOffsetMs"] + 300,
        )
        assert events[-1]["status"] == "FAILED"
    saved = client.get(f"/api/v1/meetings/{meeting}/transcripts", headers={"Authorization": f"Bearer {token}"}).json()["data"]
    assert saved == {"cursor": 0, "items": []}


async def test_ws_requires_recording_consent(client: TestClient, audio_db: None) -> None:
    token, meeting = account_meeting(client, consent=False)
    with client.websocket_connect(f"/api/v1/meetings/{meeting}/stream?token={token}") as ws:
        ws.send_json({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})
        assert ws.receive_json()["code"] == "RECORDING_CONSENT_REQUIRED"


async def test_http_finish_cannot_skip_live_tail(client: TestClient, audio_db: None) -> None:
    token, meeting = account_meeting(client)
    with client.websocket_connect(f"/api/v1/meetings/{meeting}/stream?token={token}") as ws:
        ws.send_json({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})
        assert ws.receive_json()["type"] == "audio.ready"
        response = client.post(f"/api/v1/meetings/{meeting}/finish", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "AUDIO_STREAM_ACTIVE"
        ws.send_json({"type": "end", "lastAudioSeq": 0})
        for _ in range(10):
            event = ws.receive_json()
            if event["type"] == "audio.completed":
                assert event["status"] == "COMPLETED"
                break



@pytest.mark.parametrize("amplitude, expected_segments", [(0, 0), (2000, 1)])
async def test_empty_voiced_stt_is_a_restorable_gap_but_silence_has_no_row(
    client: TestClient, audio_db: None, monkeypatch: pytest.MonkeyPatch,
    amplitude: int, expected_segments: int,
) -> None:
    stt_calls = []
    ai_calls = []

    async def empty_stt(*_, **__) -> str:
        stt_calls.append(True)
        return "   "

    async def no_ai_for_gap(*_, **__) -> None:
        ai_calls.append(True)
        raise AssertionError("Unrecognized speech must not reach AI")

    monkeypatch.setattr(WhisperStt, "transcribe", empty_stt)
    monkeypatch.setattr(meeting_service, "process_saved_segment", no_ai_for_gap)
    token, meeting = account_meeting(client)
    with client.websocket_connect(f"/api/v1/meetings/{meeting}/stream?token={token}") as ws:
        ws.send_json({"type": "start", "format": "pcm_s16le", "sampleRate": 16000, "channels": 1})
        assert ws.receive_json()["type"] == "audio.ready"
        ws.send_json({"type": "audio", "audioSeq": 1, "startMs": 0, "endMs": 300})
        ws.send_bytes(struct.pack("<h", amplitude) * 4800)
        assert ws.receive_json()["type"] == "audio.accepted"
        ws.send_json({"type": "end", "lastAudioSeq": 1})
        events = []
        for _ in range(20):
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "audio.completed":
                break
        assert events[-1]["status"] == "COMPLETED"
    saved = client.get(
        f"/api/v1/meetings/{meeting}/transcripts",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    assert len(stt_calls) == expected_segments
    assert ai_calls == []
    assert saved["cursor"] == expected_segments
    assert len(saved["items"]) == expected_segments
    if expected_segments:
        gap = saved["items"][0]
        assert gap["text"] == "" and gap["final"] is True
        assert gap["endMs"] - gap["startMs"] == 300
        assert gap["decisionJobId"] is None
        event = next(event for event in events if event["type"] == "transcript.final")
        assert event["id"] == gap["id"] and event["text"] == ""
        assert any(event.get("segmentId") == gap["id"] for event in events if event["type"] == "audio.no_transcript")
    else:
        assert not any(event["type"] == "transcript.final" for event in events)
