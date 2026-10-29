"""Jev 판단·Discord 할 일 후보·mini 활동 API의 실제 DB 동작 테스트.

회의 판단은 app.ai.judge_utterance를 실제로 부른다(#141) — 실제 모델 호출(수 초,
AI_API_KEY 필요)이라 기본값은 monkeypatch로 고정하고(_default_judge_utterance),
내용을 검증해야 하는 테스트만 따로 바꾼다. Discord·생성·STT는 여전히 더미다
(services/context_tools_stub.py, meeting_stt_stub.py).
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

import app.ai as ai
from app.db import session as db_session

pytestmark = [pytest.mark.db, pytest.mark.anyio]

PASSWORD = "PmTest-2027!"
RULES_CSV = (
    "조항,내용\n"
    "제7조 행사 취소,행사를 취소할 때는 행사 시작 7일 전까지 전체 회원에게 취소 공지를 해야 한다.\n"
).encode()
GUILD_ID = "100000000000000010"
CHANNEL_ID = "100000000000000020"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _fake_judge(
    *, route: str = "NONE", kind: str = "NO_LOOKUP", question: str | None = None,
    answer: str | None = None, sources: tuple = (),
):
    async def fake(request, *, records, progress=None):
        return ai.JudgeUtteranceResult(
            utterance_id=request.utterance.utterance_id,
            source_version=request.utterance.version,
            route=route, kind=kind, question=question, answer=answer, sources=sources,
            trace=ai.JudgeTrace(
                model="fake-model", prompt_version="fake-v1", judge_ms=1,
                tool_calls=(
                    (ai.ToolCall(tool="records.search", input=question or "", status="OK",
                                 duration_ms=1, result_count=len(sources)),)
                    if route == "RAG" else ()
                ),
            ),
        )

    return fake


@pytest.fixture(autouse=True)
def _default_judge_utterance(monkeypatch: pytest.MonkeyPatch) -> None:
    """회의 판단 테스트 대부분은 route 자체가 관심사가 아니라 NONE으로 고정해둔다."""
    monkeypatch.setattr("app.ai.judge_utterance", _fake_judge())


def _login(client: TestClient, tag: str) -> dict:
    email = f"{tag}-{uuid.uuid4().hex[:12]}@example.com"
    client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": tag}
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}


def _owner_with_club(client: TestClient) -> tuple[dict, str]:
    headers = _login(client, "ctx-owner")
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "맥락 테스트 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


def _start_meeting(client: TestClient, headers: dict, club_id: str) -> str:
    res = client.post(
        f"/api/v1/clubs/{club_id}/meetings",
        headers=headers,
        json={"title": "판단 테스트", "recordingConsentConfirmed": True},
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


def _say(client: TestClient, headers: dict, club_id: str, meeting_id: str, seq: int, text: str) -> dict:
    res = client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": seq, "startMs": 0, "endMs": 1000, "final": True, "text": text},
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


def _decision_of_job(client: TestClient, headers: dict, club_id: str, job_id: str) -> dict:
    job = client.get(f"/api/v1/agent-jobs/{job_id}", headers=headers).json()["data"]
    assert job["status"] == "SUCCEEDED"
    decision_id = job["result"]["contextDecisionId"]
    return client.get(
        f"/api/v1/clubs/{club_id}/context-decisions/{decision_id}", headers=headers
    ).json()["data"]


async def test_회칙을_올리면_INDEXED로_바뀌고_RAG_판단이_출처를_인용한다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_index_record(request):
        return ai.IndexRecordResult(
            chunks=(
                ai.IndexedChunk(
                    text=request.blocks[0].text, location=request.blocks[0].location,
                    block_indexes=(0,), embedding=tuple([0.1] * ai.EMBEDDING_DIMENSIONS),
                ),
            )
        )

    monkeypatch.setattr("app.ai.index_record", fake_index_record)

    headers, club_id = _owner_with_club(client)
    upload = client.post(
        "/api/v1/records",
        headers=headers,
        data={"clubId": club_id, "category": "RULES"},
        files={"file": ("rules.csv", RULES_CSV, "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    record_id = upload.json()["data"]["id"]
    detail = client.get(f"/api/v1/records/{record_id}", headers=headers).json()["data"]
    # 파싱만이 아니라 app.ai.index_record로 청크까지 저장됐다(#141) — 실제 임베딩
    # 호출은 DbRecordSearchPort 테스트(test_record_chunks.py)에서 따로 확인한다.
    assert detail["parseStatus"] == "INDEXED"

    monkeypatch.setattr(
        "app.ai.judge_utterance",
        _fake_judge(
            route="RAG", kind="ANSWER",
            question="행사 취소 공지는 며칠 전에 해야 하나요?",
            answer="7일 전까지 공지해야 합니다.",
            sources=(
                ai.RecordSource(
                    record_id=record_id, file_name="rules.csv",
                    location=ai.SourceLocation(label="2행"),
                ),
            ),
        ),
    )
    meeting_id = _start_meeting(client, headers, club_id)
    segment = _say(
        client, headers, club_id, meeting_id, 1,
        "우리 동아리 회칙에서 행사 취소 공지는 며칠 전에 해야 한다고 되어 있나요?",
    )
    decision = _decision_of_job(client, headers, club_id, segment["jobId"])

    assert decision["route"] == "RAG"
    assert decision["kind"] == "ANSWER"
    assert decision["sources"] == [
        {"sourceId": segment["sourceId"], "sourceVersion": segment["sourceVersion"]}
    ]
    assert decision["citations"][0]["recordId"] == record_id
    assert decision["citations"][0]["location"]["label"] == "2행"
    assert "7일 전" in decision["output"]


async def test_음성_청크를_올리면_전사와_판단이_이어지고_같은_청크_재전송은_재사용된다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    meeting_id = _start_meeting(client, headers, club_id)
    chunk = {"seq": "1", "startMs": "0", "endMs": "5000"}
    audio = ("chunk-001.wav", b"RIFF-fake-audio", "audio/wav")

    first = client.post(
        f"/api/v1/meetings/{meeting_id}/audio-chunks",
        headers=headers, data=chunk, files={"file": audio},
    )
    assert first.status_code == 202, first.text
    stt_job = client.get(
        f"/api/v1/agent-jobs/{first.json()['data']['jobId']}", headers=headers
    ).json()["data"]
    assert stt_job["kind"] == "MEETING_STT"
    assert stt_job["status"] == "SUCCEEDED"
    # 판단(CONTEXT_DECISION)은 별도 작업이라 STT 작업 결과엔 더 이상 안 담는다(#141
    # — 백그라운드로 따로 돈다).
    assert "contextDecisionIds" not in stt_job["result"]

    retry = client.post(
        f"/api/v1/meetings/{meeting_id}/audio-chunks",
        headers=headers, data=chunk, files={"file": audio},
    )
    assert retry.json()["data"] == first.json()["data"]

    transcripts = client.get(
        f"/api/v1/meetings/{meeting_id}/transcripts?afterSeq=0", headers=headers
    ).json()["data"]
    assert len(transcripts["items"]) == 1
    assert transcripts["items"][0]["final"] is True
    assert transcripts["items"][0]["decisionJobId"]


async def test_afterSeq_이후에_고친_전사도_다시_내려온다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    meeting_id = _start_meeting(client, headers, club_id)
    _say(client, headers, club_id, meeting_id, 1, "첫 발화")
    _say(client, headers, club_id, meeting_id, 2, "둘째 발화")
    cursor = client.get(
        f"/api/v1/meetings/{meeting_id}/transcripts?afterSeq=0", headers=headers
    ).json()["data"]["cursor"]

    client.post(
        f"/api/v1/test-support/clubs/{club_id}/meetings/{meeting_id}/transcripts",
        headers=headers,
        json={"seq": 1, "startMs": 0, "endMs": 1000, "final": True, "text": "첫 발화 정정", "expectedVersion": 1},
    )
    changed = client.get(
        f"/api/v1/meetings/{meeting_id}/transcripts?afterSeq={cursor}", headers=headers
    ).json()["data"]

    assert [item["seq"] for item in changed["items"]] == [1]
    assert changed["items"][0]["version"] == 2
    assert changed["cursor"] == cursor + 1


def _fixture_connection(client: TestClient, headers: dict, club_id: str) -> str:
    res = client.post(
        f"/api/v1/test-support/clubs/{club_id}/discord-connections",
        headers=headers,
        json={"mode": "FIXTURE", "guildId": GUILD_ID, "channelIds": [CHANNEL_ID], "enabled": True},
    )
    assert res.status_code == 201, res.text
    assert res.json()["data"]["status"] == "MONITORING"
    return res.json()["data"]["id"]


def _discord_event(client: TestClient, headers: dict, club_id: str, connection_id: str, n: int, text: str):
    return client.post(
        f"/api/v1/test-support/clubs/{club_id}/discord-events",
        headers=headers,
        json={
            "connectionId": connection_id,
            "eventType": "MESSAGE_CREATE",
            "eventId": f"evt-{n}",
            "guildId": GUILD_ID,
            "channelId": CHANNEL_ID,
            "messageId": f"10000000000000000{n}",
            "authorId": "100000000000000099",
            "sourceOccurredAt": f"2026-10-12T01:0{n}:00Z",
            "content": text,
        },
    )


async def test_Discord_대화_맥락에서_할_일_후보를_만들고_수락은_기록만_한다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    connection_id = _fixture_connection(client, headers, club_id)

    first = _discord_event(client, headers, club_id, connection_id, 1, "토요일 모임 장소가 아직 확정되지 않았어요.")
    second = _discord_event(client, headers, club_id, connection_id, 2, "그럼 운영진 중 누군가 후보 장소를 확인해야겠네요.")
    assert first.status_code == 202 and second.status_code == 202

    decisions = client.get(
        f"/api/v1/clubs/{club_id}/context-decisions?sourceType=DISCORD_MESSAGE&connectionId={connection_id}",
        headers=headers,
    ).json()["data"]
    assert [d["route"] for d in decisions] == ["NONE", "LLM"]
    # 두 번째 판단은 앞 메시지까지 근거로 본다.
    assert len(decisions[1]["sources"]) == 2

    tasks = client.get(
        f"/api/v1/clubs/{club_id}/task-suggestions?sourceType=DISCORD_MESSAGE&status=PROPOSED",
        headers=headers,
    ).json()["data"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["suggestedAssignee"] is None and task["dueDate"] is None

    renamed = client.patch(
        f"/api/v1/clubs/{club_id}/task-suggestions/{task['id']}",
        headers=headers,
        json={"expectedVersion": task["version"], "title": "토요일 모임 장소 후보 2곳 확인"},
    ).json()["data"]
    assert renamed["version"] == task["version"] + 1
    assert renamed["status"] == "PROPOSED"

    accepted = client.post(
        f"/api/v1/clubs/{club_id}/task-suggestions/{task['id']}/accept",
        headers=headers,
        json={"expectedVersion": renamed["version"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "ACCEPTED"

    # 같은 메시지를 다시 수집해도 새 판단·후보를 만들지 않는다.
    again = _discord_event(client, headers, club_id, connection_id, 2, "그럼 운영진 중 누군가 후보 장소를 확인해야겠네요.")
    assert again.json()["data"]["duplicate"] is True
    assert again.json()["data"]["jobId"] is None


async def test_모니터링을_중지하면_새_메시지를_분석하지_않는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    connection_id = _fixture_connection(client, headers, club_id)
    paused = client.patch(
        f"/api/v1/discord-connections/{connection_id}",
        headers=headers,
        json={"expectedVersion": 1, "enabled": False},
    ).json()["data"]
    assert paused["status"] == "PAUSED"

    res = _discord_event(client, headers, club_id, connection_id, 1, "확인해야 할 일이 있어요.")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONNECTION_DISABLED"


async def test_실제_Discord_연결의_sync는_수집기가_없어_실패로_남는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    created = client.post(
        f"/api/v1/clubs/{club_id}/discord-connections",
        headers=headers,
        json={"guildId": "1", "channelIds": ["2"], "botProfile": "configured-test-bot", "enabled": True},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["status"] == "DISCONNECTED"

    sync = client.post(
        f"/api/v1/discord-connections/{created.json()['data']['id']}/sync", headers=headers, json={}
    )
    assert sync.status_code == 202
    job = client.get(f"/api/v1/agent-jobs/{sync.json()['data']['jobId']}", headers=headers).json()["data"]
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "DISCORD_COLLECTOR_UNAVAILABLE"


async def test_활동_snapshot은_검토할_할_일이_있으면_ATTENTION_없으면_IDLE이다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    empty = client.get(f"/api/v1/clubs/{club_id}/activity", headers=headers).json()["data"]
    assert empty == {
        "cursor": "0",
        "characterState": "IDLE",
        "jobs": [],
        "connections": [],
        "proposedTaskCount": 0,
    }

    connection_id = _fixture_connection(client, headers, club_id)
    _discord_event(client, headers, club_id, connection_id, 1, "누군가 장소를 확인해야겠네요.")
    snapshot = client.get(f"/api/v1/clubs/{club_id}/activity", headers=headers).json()["data"]

    assert snapshot["characterState"] == "ATTENTION"
    assert snapshot["proposedTaskCount"] == 1
    # cursor는 전체 활동 이벤트의 순번이라 이 동아리 이벤트 수와 같지 않다.
    assert int(snapshot["cursor"]) > 0
    assert snapshot["connections"] == [
        {"id": connection_id, "status": "MONITORING", "enabled": True}
    ]


async def test_다른_동아리의_작업은_조회할_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = _owner_with_club(client)
    meeting_id = _start_meeting(client, headers, club_id)
    segment = _say(client, headers, club_id, meeting_id, 1, "회의 시작합니다")
    outsider = _login(client, "ctx-outsider")

    res = client.get(f"/api/v1/agent-jobs/{segment['jobId']}", headers=outsider)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"
