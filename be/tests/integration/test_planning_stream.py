"""계획 대화·버튼 생성 SSE 엔드포인트 테스트 (#266, #284).

AI 공개 함수는 고정 응답으로 바꾸고, 진행 알림·답변 조각을 포트로 직접 보낸다.
확인하는 것은 BE의 이벤트 순서, 스트림 전/중 오류, 저장·멱등, 연결이 끊겨도 저장되는지다.
"""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.ai as ai
from app.core.exceptions import VersionConflict
from app.db.session import get_sessionmaker
from app.main import app
from app.models.common import IdempotencyKey
from app.services import planning_service, planning_stream
from tests.integration.test_events_planning import (
    PASSWORD,
    _create_event,
    _fake_chat_result,
    _fake_generation_result,
    _owner_with_club,
    app_db,  # noqa: F401  (fixture)
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CHAT_BODY = {"messageId": "msg-1", "message": "인원 60명으로 바꿔줘", "baseRevision": 0}


def parse(text: str) -> list[tuple[str, dict | None]]:
    """SSE 본문을 (event, data) 목록으로. 주석 줄(heartbeat)은 ('comment', None)."""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(":"):
            events.append(("comment", None))
            continue
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def post_stream(client: TestClient, path: str, headers: dict, body: dict) -> httpx.Response:
    res = client.post(path, headers=headers, json=body)
    return res


def progress_event(kind="condition_applied", status="completed", text="예상 인원 반영했어요"):
    return ai.PlanningProgress(operation_id="call_1", kind=kind, status=status, text=text,
        condition_draft=ai.PlanningDraft(conditions=ai.PlanningConditions(headcount=60))
        if kind == "condition_applied" and status == "completed" else None)


def fake_chat(calls: list | None = None, *, error: Exception | None = None, delay: float = 0):
    async def chat_planning(request, *, records=None, progress=None):
        if calls is not None:
            calls.append(progress)
        if progress is not None:
            await progress.progress(progress_event())
            await progress.reply_delta("예상 인원을 ")
            await progress.reply_delta("60명으로 바꿨어요.")
        if delay:
            await asyncio.sleep(delay)
        if error is not None:
            raise error
        return _fake_chat_result(event_type="MT", headcount=60,
                                 reply="예상 인원을 60명으로 바꿨어요.")
    return chat_planning


async def test_채팅_스트림은_진행_답변_조각_뒤에_JSON과_같은_결과를_보내고_저장한다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    monkeypatch.setattr("app.ai.chat_planning", fake_chat())

    streamed_event = _create_event(client, headers, club_id)
    res = post_stream(client, f"/api/v1/events/{streamed_event}/plan/chat/stream", headers, CHAT_BODY)

    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    events = parse(res.text)
    assert [name for name, _ in events] == ["progress", "reply_delta", "reply_delta", "done"]
    progress = events[0][1]
    assert progress["operationId"] == "call_1"
    assert progress["kind"] == "condition_applied" and progress["status"] == "completed"
    assert progress["text"] == "예상 인원 반영했어요"
    assert progress["conditionDraft"]["conditions"]["headcount"] == 60
    assert progress["conditionDraft"]["conditions"]["feePerPerson"] is None
    assert "".join(data["text"] for name, data in events if name == "reply_delta") == \
        events[-1][1]["reply"]

    # 같은 고정 결과를 JSON 경로로 받은 data와 done이 같아야 한다.
    json_event = _create_event(client, headers, club_id)
    json_res = client.post(f"/api/v1/events/{json_event}/plan/chat", headers=headers, json=CHAT_BODY)
    assert events[-1][1] == json_res.json()["data"]

    plan = client.get(f"/api/v1/events/{streamed_event}/plan", headers=headers).json()["data"]
    assert plan["baseRevision"] == 1
    messages = client.get(f"/api/v1/events/{streamed_event}/plan/messages", headers=headers)
    assert [m["content"] for m in messages.json()["data"]] == [
        "인원 60명으로 바꿔줘", "예상 인원을 60명으로 바꿨어요."]


async def test_JSON_경로는_progress_없이_AI를_부른다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    calls: list = []
    monkeypatch.setattr("app.ai.chat_planning", fake_chat(calls))

    res = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=headers, json=CHAT_BODY)

    assert res.status_code == 200, res.text
    assert calls == [None]


async def test_스트림을_열기_전_revision_불일치는_일반_409(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    calls: list = []
    monkeypatch.setattr("app.ai.chat_planning", fake_chat(calls))

    res = post_stream(client, f"/api/v1/events/{event_id}/plan/chat/stream", headers,
                      {**CHAT_BODY, "baseRevision": 5})

    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"
    assert calls == []


@pytest.mark.parametrize("error,code", [
    (ai.AIRetryableError("모델 연결 실패"), "AI_UNAVAILABLE"),
    (RuntimeError("사용자 대화가 섞인 원문"), "INTERNAL_ERROR"),
])
async def test_스트림_중_AI_실패는_error_이벤트이고_같은_키로_다시_시도할_수_있다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch, error, code
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    keyed = {**headers, "Idempotency-Key": "stream-retry"}
    monkeypatch.setattr("app.ai.chat_planning", fake_chat(error=error))

    res = post_stream(client, f"/api/v1/events/{event_id}/plan/chat/stream", keyed, CHAT_BODY)

    events = parse(res.text)
    assert res.status_code == 200
    assert events[-1][0] == "error" and events[-1][1]["code"] == code
    assert "원문" not in res.text
    assert "done" not in [name for name, _ in events]
    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers).json()["data"]
    assert plan["baseRevision"] == 0

    # 키를 풀었으므로 같은 키·같은 본문으로 다시 보내면 처음부터 처리한다.
    monkeypatch.setattr("app.ai.chat_planning", fake_chat())
    retry = parse(post_stream(client, f"/api/v1/events/{event_id}/plan/chat/stream", keyed,
                              CHAT_BODY).text)
    assert retry[-1][0] == "done"


async def test_저장_직전_revision_충돌은_error_이벤트이고_키를_푼다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    monkeypatch.setattr("app.ai.chat_planning", fake_chat())

    async def conflict(*args, **kwargs):
        # AI를 기다리는 사이 다른 요청이 먼저 저장한 경우(_finish의 revision 재확인).
        raise VersionConflict()

    monkeypatch.setattr(planning_service, "_finish", conflict)

    res = post_stream(client, f"/api/v1/events/{event_id}/plan/chat/stream",
                      {**headers, "Idempotency-Key": "stream-conflict"}, CHAT_BODY)

    events = parse(res.text)
    # 진행 알림과 답변 조각은 이미 보냈다. FE는 error를 받으면 이를 버리고 스냅샷을 다시 불러온다.
    assert [name for name, _ in events] == ["progress", "reply_delta", "reply_delta", "error"]
    assert events[-1][1]["code"] == "VERSION_CONFLICT"
    async with get_sessionmaker()() as session:
        left = await session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.idempotency_key == "stream-conflict"))
    assert left is None


async def test_같은_키로_끝난_요청을_다시_보내면_done_하나만_보낸다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    calls: list = []
    monkeypatch.setattr("app.ai.chat_planning", fake_chat(calls))
    keyed = {**headers, "Idempotency-Key": "stream-replay"}
    path = f"/api/v1/events/{event_id}/plan/chat/stream"

    first = parse(post_stream(client, path, keyed, CHAT_BODY).text)
    second = parse(post_stream(client, path, keyed, CHAT_BODY).text)

    assert len(calls) == 1
    assert [name for name, _ in second] == ["done"]
    assert second[0][1] == first[-1][1]
    # 스트림과 JSON 경로는 같은 작업이라 멱등키를 공유한다. JSON으로 다시 물어도 같은 결과다.
    replayed = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=keyed, json=CHAT_BODY)
    assert replayed.json()["data"] == first[-1][1]
    assert len(calls) == 1


async def test_오래_조용하면_heartbeat_주석을_보낸다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    monkeypatch.setattr("app.ai.chat_planning", fake_chat(delay=0.2))
    monkeypatch.setattr(planning_stream, "HEARTBEAT_SECONDS", 0.05)

    events = parse(post_stream(client, f"/api/v1/events/{event_id}/plan/chat/stream", headers,
                               CHAT_BODY).text)

    assert ("comment", None) in events
    assert events[-1][0] == "done"


async def test_버튼_생성_스트림은_생성_진행과_결과를_보낸다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request, *, progress=None):
        await progress.progress(progress_event("generation_started", "running", "계획 초안을 만들고 있어요"))
        # 생각을 마치고 초안을 쓰기 시작한 순간(#388). 같은 작업의 진행 중 줄을 바꾼다.
        await progress.progress(progress_event("generation_writing", "running", "초안을 작성하는 중이에요"))
        await progress.progress(progress_event("generation_finished", "completed", "초안 2단계를 만들었어요"))
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)

    res = post_stream(client, f"/api/v1/events/{event_id}/plan/generate/stream", headers,
                      {"baseRevision": 0})

    events = parse(res.text)
    assert [(name, data.get("kind"), data.get("status")) for name, data in events[:3]] == [
        ("progress", "generation_started", "running"), ("progress", "generation_writing", "running"),
        ("progress", "generation_finished", "completed")]
    assert events[1][1]["text"] == "초안을 작성하는 중이에요"
    assert events[-1][0] == "done"
    assert events[-1][1]["generationResult"]["status"] == "generated"
    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers).json()["data"]
    assert plan["summary"]["totalSteps"] == 2


async def test_연결이_끊겨도_AI_작업은_끝까지_진행해_저장한다(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TestClient는 응답을 끝까지 모아 받으므로, 같은 이벤트 루프에서 ASGI 앱을 직접 불러
    # 첫 이벤트를 보낸 뒤 연결이 끊긴 상황(send에서 OSError)을 만든다.
    release = asyncio.Event()

    async def slow_chat(request, *, records=None, progress=None):
        await progress.progress(progress_event())
        await release.wait()
        return _fake_chat_result(event_type="MT", headcount=60, reply="저장됐어요.")

    monkeypatch.setattr("app.ai.chat_planning", slow_chat)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        email = f"stream-cut-{id(release)}@example.com"
        await http.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "끊김"})
        token = (await http.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
                 ).json()["data"]["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}
        club_id = (await http.post("/api/v1/clubs", headers=headers, json={"name": "끊김 동아리"})
                   ).json()["data"]["id"]
        event_id = (await http.post("/api/v1/events", headers=headers, json={"clubId": club_id})
                    ).json()["data"]["id"]

        body = json.dumps(CHAT_BODY).encode()
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": f"/api/v1/events/{event_id}/plan/chat/stream",
            "raw_path": b"", "root_path": "", "query_string": b"", "server": ("test", 80),
            "client": ("test", 1234),
            "headers": [(b"authorization", f"Bearer {token}".encode()),
                        (b"content-type", b"application/json"),
                        (b"idempotency-key", b"stream-cut"),
                        (b"content-length", str(len(body)).encode())],
        }
        sent: list[bytes] = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                sent.append(message["body"])
                raise OSError("client went away")

        with pytest.raises(Exception):
            await app(scope, receive, send)
        assert sent and b"event: progress" in sent[0]

        # 연결이 끊긴 뒤에 AI가 끝난다. 작업은 남아 있다가 저장까지 한다.
        assert planning_stream._running
        lookup_path = f"/api/v1/events/{event_id}/plan/requests/stream-cut"
        # #342: 끊긴 FE는 같은 키로 결과만 조회한다. 아직 AI를 기다리는 중이면 processing이다.
        waiting = (await http.get(lookup_path, headers=headers)).json()["data"]
        assert waiting == {"status": "processing", "result": None}
        release.set()
        await asyncio.wait_for(asyncio.gather(*planning_stream._running), 5)

        plan = (await http.get(f"/api/v1/events/{event_id}/plan", headers=headers)).json()["data"]
        assert plan["baseRevision"] == 1
        # 저장이 끝나면 그 요청이 받았어야 할 응답을 그대로 돌려준다.
        saved = (await http.get(lookup_path, headers=headers)).json()["data"]
        assert saved["status"] == "completed"
        assert saved["result"]["reply"] == "저장됐어요."
        assert saved["result"]["baseRevision"] == 1
        # FE가 같은 키로 다시 요청하면 저장된 결과를 done 하나로 받는다.
        replay = await http.post(f"/api/v1/events/{event_id}/plan/chat/stream",
                                 headers={**headers, "Idempotency-Key": "stream-cut"}, json=CHAT_BODY)
        assert [name for name, _ in parse(replay.text)] == ["done"]


async def test_조건_완료의_잠정_메타와_해제값을_전달하고_다른_알림에는_초안을_넣지_않는다():
    from app.ai.contracts import ConditionMeta, MessageEvidence

    queue = asyncio.Queue()
    port = planning_stream._QueuePort(queue)
    draft = ai.PlanningDraft(
        conditions=ai.PlanningConditions(headcount=50, fee_per_person=0),
        condition_meta={"headcount": ConditionMeta(status="tentative",
            evidence=MessageEvidence(message_id="u1", quote="일단 50명"))},
    )
    await port.progress(ai.PlanningProgress(operation_id="c1", kind="condition_applied",
        status="completed", text="예상 인원 · 참가비 반영했어요", condition_draft=draft))
    payload = parse(queue.get_nowait())[0][1]["conditionDraft"]
    assert payload["conditions"]["headcount"] == 50
    assert payload["conditions"]["feePerPerson"] == 0
    assert payload["conditions"]["startDate"] is None
    assert payload["conditionMeta"]["headcount"] == {
        "status": "tentative", "evidenceMessageId": "u1", "evidenceQuote": "일단 50명"}
    for kind, status in [("condition_applied", "skipped"), ("search_started", "running"),
                         ("search_finished", "empty"), ("generation_finished", "completed")]:
        await port.progress(ai.PlanningProgress(operation_id="other", kind=kind,
                                                status=status, text="처리 상태"))
        assert "conditionDraft" not in parse(queue.get_nowait())[0][1]
