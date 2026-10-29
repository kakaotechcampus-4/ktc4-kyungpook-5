"""P1·P2 행사 계획 API 테스트 (#187).

app.ai.chat_planning()/generate_planning_preview()는 실제 모델 호출이라(AI_API_KEY
필요, 턴당 수 초~수십 초) 결과를 monkeypatch로 고정해 저장·동시성·멱등성 로직만
검증한다. 실제 모델과의 연동 자체는 app/ai/tests에서 따로 확인한다.
"""

import hashlib
import json
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import anyio
import pytest
from fastapi.testclient import TestClient

import app.ai as ai
from app.db import session as db_session
from app.models.common import IdempotencyKey

pytestmark = [pytest.mark.db, pytest.mark.anyio]

PASSWORD = "PmTest-2027!"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _login(client: TestClient, tag: str) -> dict:
    email = f"{tag}-{uuid.uuid4().hex[:12]}@example.com"
    client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": tag}
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}


def _owner_with_club(client: TestClient) -> tuple[dict, str]:
    headers = _login(client, "plan-owner")
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "계획 테스트 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


def _create_event(client: TestClient, headers: dict, club_id: str) -> str:
    res = client.post("/api/v1/events", headers=headers, json={"clubId": club_id})
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


def _fake_chat_result(
    *, event_type: str | None = None, headcount: int | None = None,
    reply: str = "알겠습니다.", generation_result=None,
) -> ai.PlanningPublicResult:
    from app.ai.contracts import PlanningGenerationState, PlanningStatePayload

    conditions = ai.PlanningConditions(event_type=event_type, headcount=headcount)
    draft = ai.PlanningDraft(conditions=conditions)
    view = ai.PlanningView(
        reply=reply,
        draft=draft,
        changed_fields=(),
        record_lookup=None,
        generation_readiness=ai.PlanningGenerationReadiness(
            can_generate=bool(event_type),
            reasons=() if event_type else ("event_type_missing",),
        ),
        generation_result=generation_result,
        preview_is_current=False,
        # 실제 공개 함수는 매번 채운다(public_workflow.py). 보관 이력 수와 같아야 한다.
        history_usage=ai.PlanningHistoryUsage.from_count(0),
    )
    next_state = ai.PlanningResumeState(
        club_id="club-x", event_id="event-x", conversation_id="conv-x",
        payload=PlanningStatePayload(
            basis_draft=draft, history=(), generation=PlanningGenerationState()
        ),
    )
    return ai.PlanningPublicResult(
        request_id="req-x", base_revision=0, view=view, next_state=next_state
    )


def _fake_generation_result() -> ai.PlanningPublicResult:
    from app.ai.contracts import (
        ButtonGenerationTrigger,
        EventPlanPreview,
        ExcludedPreviewStep,
        PlanAction,
        PlanGenerationResult,
        PreviewStep,
    )
    from app.core.enums import ActionType, StepActor, StepCode, StepPhase

    preview = EventPlanPreview(
        id="preview-1",
        basis_draft=ai.PlanningDraft(
            conditions=ai.PlanningConditions(event_type="MT", headcount=30)
        ),
        trigger=ButtonGenerationTrigger(request_id="click-1"),
        steps=(
            PreviewStep(
                code=StepCode.RESEARCH_VENUE,
                purpose="장소 후보를 찾는다",
                name="장소 조사",
                phase=StepPhase.PREPARATION,
                actor=StepActor.AI,
                actions=(
                    PlanAction(type=ActionType.NOTICE, title="장소 공지"),
                ),
            ),
            PreviewStep(
                code=StepCode.COLLECT_FEES,
                purpose="참가비를 걷는다",
                name="참가비 수금",
                phase=StepPhase.RECRUITING,
                actor=StepActor.APPROVAL_REQUIRED,
                actions=(
                    PlanAction(type=ActionType.TRANSFER, title="참가비 송금"),
                ),
            ),
        ),
        excluded_steps=(
            ExcludedPreviewStep(
                code=StepCode.DEMAND_SURVEY,
                name="사전 수요 조사",
                reason="이미 참여 의사를 확인했어요.",
            ),
        ),
        warnings=("일정이 비어 있습니다",),
    )
    generation_result = PlanGenerationResult(status="generated", preview=preview)
    return _fake_chat_result(
        event_type="MT", headcount=30, reply=None, generation_result=generation_result
    )


async def test_행사_생성_시_제목을_비우면_기본값이_들어간다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)

    res = client.post("/api/v1/events", headers=headers, json={"clubId": club_id})

    assert res.status_code == 201, res.text
    assert "새 행사" in res.json()["data"]["title"]


async def test_대화_한_턴으로_조건이_저장되고_revision이_오른다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_chat_planning(request, *, records=None):
        return _fake_chat_result(event_type="MT", headcount=30)

    monkeypatch.setattr("app.ai.chat_planning", fake_chat_planning)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/chat",
        headers=headers,
        json={"messageId": "msg-1", "message": "MT 가려고, 30명", "baseRevision": 0},
    )

    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert body["baseRevision"] == 1
    assert body["draft"]["conditions"]["headcount"] == 30
    assert body["generationReadiness"]["canGenerate"] is True


async def test_base_revision이_다르면_409(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_chat_planning(request, *, records=None):
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat_planning)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/chat",
        headers=headers,
        json={"messageId": "msg-1", "message": "MT 가자", "baseRevision": 5},
    )

    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_같은_Idempotency_Key면_AI를_다시_부르지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    call_count = 0

    async def fake_chat_planning(request, *, records=None):
        nonlocal call_count
        call_count += 1
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat_planning)

    body = {"messageId": "msg-1", "message": "MT 가자", "baseRevision": 0}
    first = client.post(
        f"/api/v1/events/{event_id}/plan/chat",
        headers={**headers, "Idempotency-Key": "idem-1"},
        json=body,
    )
    second = client.post(
        f"/api/v1/events/{event_id}/plan/chat",
        headers={**headers, "Idempotency-Key": "idem-1"},
        json=body,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert call_count == 1


async def test_생성_성공하면_Step_Action이_규칙대로_만들어진다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request):
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/generate",
        headers=headers,
        json={"baseRevision": 0},
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["generationResult"]["status"] == "generated"

    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)
    assert plan.status_code == 200, plan.text
    summary = plan.json()["data"]["summary"]
    assert summary["totalSteps"] == 2
    assert summary["aiSteps"] == 1
    assert summary["approvalSteps"] == 1
    assert plan.json()["data"]["warnings"] == ["일정이 비어 있습니다"]


async def test_다른_동아리_사람은_행사_계획에_접근할_수_없다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    outsider_headers = _login(client, "plan-outsider")

    res = client.get(f"/api/v1/events/{event_id}/plan", headers=outsider_headers)

    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


async def test_계획_이력과_단계는_소속만_순서대로_조회한다(client, app_db, monkeypatch):
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    async def fake_chat(request, *, records=None):
        return _fake_chat_result(event_type="MT", headcount=20, reply="장소를 정해요.")
    monkeypatch.setattr("app.ai.chat_planning", fake_chat)
    res = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=headers,
                      json={"messageId":"m1","message":"MT 20명","baseRevision":0})
    assert res.status_code == 200
    messages = client.get(f"/api/v1/events/{event_id}/plan/messages", headers=headers)
    assert messages.status_code == 200
    assert [(m["role"],m["content"]) for m in messages.json()["data"]] == [("USER","MT 20명"),("ASSISTANT","장소를 정해요.")]
    steps = client.get(f"/api/v1/events/{event_id}/plan/steps", headers=headers)
    assert steps.status_code == 200 and steps.json()["data"] == []
    outsider = _login(client,"outsider")
    assert client.get(f"/api/v1/events/{event_id}/plan/messages", headers=outsider).status_code == 403
    assert client.get(f"/api/v1/events/{event_id}/plan/steps", headers=outsider).status_code == 403


async def test_계획_복원에_현재_정책으로_준비상태를_계산한다(client, app_db, monkeypatch):
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    initial = client.get(f'/api/v1/events/{event_id}/plan', headers=headers)
    assert initial.status_code == 200 and initial.json()['data']['generationReadiness'] is None
    async def fake_chat(request, *, records=None):
        return _fake_chat_result(event_type='MT', headcount=30)
    monkeypatch.setattr('app.ai.chat_planning', fake_chat)
    result = client.post(f'/api/v1/events/{event_id}/plan/chat', headers=headers,
                         json={'messageId':'restore-readiness','message':'MT 30명','baseRevision':0})
    assert result.status_code == 200
    restored = client.get(f'/api/v1/events/{event_id}/plan', headers=headers)
    assert restored.status_code == 200
    # 구 정책에서 저장된 true라도 현재 조건을 기준으로 다시 계산한다.
    assert result.json()['data']['generationReadiness']['canGenerate'] is True
    assert restored.json()['data']['generationReadiness'] == {
        'canGenerate': False,
        'reasons': ['dates_unanswered', 'location_unanswered'],
    }


# --- #187 후속: 멱등키 동시 요청·입력 검증·기준일·새 응답 필드 ----------------

CHAT_BODY = {"messageId": "msg-1", "message": "MT 가자", "baseRevision": 0}


def _chat(client: TestClient, headers: dict, event_id: str, key: str | None = None):
    extra = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/v1/events/{event_id}/plan/chat", headers={**headers, **extra}, json=CHAT_BODY
    )


async def test_같은_키의_첫_요청이_처리_중이면_AI를_다시_부르지_않고_409(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#203 멘토 리뷰: 첫 요청이 AI를 기다리는 동안 같은 키로 다시 보내면 두 번 호출됐다."""
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    started, release = threading.Event(), threading.Event()
    call_count = 0

    async def slow_chat_planning(request, *, records=None):
        nonlocal call_count
        call_count += 1
        started.set()
        await anyio.to_thread.run_sync(release.wait)
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", slow_chat_planning)

    first: list = []
    worker = threading.Thread(
        target=lambda: first.append(_chat(client, headers, event_id, "idem-slow"))
    )
    worker.start()
    assert started.wait(10)

    second = _chat(client, headers, event_id, "idem-slow")
    release.set()
    worker.join(10)

    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "IDEMPOTENCY_IN_PROGRESS"
    assert first[0].status_code == 200, first[0].text
    assert call_count == 1
    # 처리가 끝난 뒤 같은 키로 다시 보내면 저장된 응답을 그대로 받는다.
    replay = _chat(client, headers, event_id, "idem-slow")
    assert replay.json() == first[0].json()
    assert call_count == 1


async def _leftover_processing_key(
    client: TestClient, headers: dict, club_id: str, key: str, *, age: timedelta
) -> None:
    """처리하던 서버가 사라져 PROCESSING으로 남은 키를 흉내 낸다."""
    members = client.get(f"/api/v1/clubs/{club_id}/members", headers=headers).json()
    body_hash = hashlib.sha256(json.dumps(CHAT_BODY, sort_keys=True).encode()).hexdigest()
    async with db_session.get_sessionmaker()() as session:
        session.add(
            IdempotencyKey(
                club_id=club_id,
                member_id=members["data"][0]["id"],
                endpoint="POST /events/{event_id}/plan/chat",
                idempotency_key=key,
                request_body_hash=body_hash,
                status="PROCESSING",
                modified_at=datetime.now(UTC) - age,
            )
        )
        await session.commit()


async def test_오래_남은_처리_중_키는_새_요청이_이어받는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_chat_planning(request, *, records=None):
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", fake_chat_planning)
    await _leftover_processing_key(
        client, headers, club_id, "idem-fresh", age=timedelta(seconds=10)
    )
    await _leftover_processing_key(
        client, headers, club_id, "idem-stale", age=timedelta(minutes=10)
    )

    assert _chat(client, headers, event_id, "idem-fresh").status_code == 409
    assert _chat(client, headers, event_id, "idem-stale").status_code == 200


async def test_AI가_실패하면_같은_키로_다시_시도할_수_있다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    call_count = 0

    async def flaky_chat_planning(request, *, records=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ai.AIRetryableError("일시 오류")
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.ai.chat_planning", flaky_chat_planning)

    failed = _chat(client, headers, event_id, "idem-retry")
    retried = _chat(client, headers, event_id, "idem-retry")

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "AI_UNAVAILABLE"
    assert retried.status_code == 200, retried.text
    assert call_count == 2


@pytest.mark.parametrize(
    "body",
    [
        {"messageId": "msg-1", "message": "   ", "baseRevision": 0},
        {"messageId": "msg-1", "message": "가" * 4001, "baseRevision": 0},
        {"messageId": " ", "message": "MT 가자", "baseRevision": 0},
        {"messageId": "msg-1", "message": "MT 가자", "baseRevision": -1},
    ],
)
async def test_잘못된_대화_입력은_422(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch, body: dict
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def must_not_call(request, *, records=None):
        raise AssertionError("검증에서 막혀야 한다")

    monkeypatch.setattr("app.ai.chat_planning", must_not_call)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/chat", headers=headers, json=body
    )

    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_기준일은_KST_날짜로_넘긴다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    seen: list[date] = []

    class KstEarlyMorning(datetime):
        """UTC 10/29 15:30 = KST 10/30 00:30. UTC 기준이면 하루 전이 된다."""

        @classmethod
        def now(cls, tz=None):
            moment = datetime(2026, 10, 29, 15, 30, tzinfo=UTC)
            return moment.astimezone(tz) if tz else moment

    async def fake_chat_planning(request, *, records=None):
        seen.append(request.reference_date)
        return _fake_chat_result(event_type="MT")

    monkeypatch.setattr("app.services.planning_service.datetime", KstEarlyMorning)
    monkeypatch.setattr("app.ai.chat_planning", fake_chat_planning)

    assert _chat(client, headers, event_id).status_code == 200
    assert seen == [date(2026, 10, 30)]


async def test_대화_한도_사용량과_제외_단계_이름이_응답과_재접속_화면에_있다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request):
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)

    res = client.post(
        f"/api/v1/events/{event_id}/plan/generate", headers=headers, json={"baseRevision": 0}
    )
    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers).json()["data"]

    usage = {"messageCount": 0, "maxMessages": 60, "nearLimit": False}
    assert res.json()["data"]["historyUsage"] == usage
    assert plan["historyUsage"] == usage
    assert plan["excludedSteps"] == [
        {"code": "DEMAND_SURVEY", "name": "사전 수요 조사", "reason": "이미 참여 의사를 확인했어요."}
    ]


async def test_이름_없이_저장된_예전_제외_단계도_읽을_수_있다(
    client: TestClient, app_db: None
) -> None:
    from app.models.events import Event

    headers, club_id = _owner_with_club(client)
    event_id = _create_event(client, headers, club_id)
    async with db_session.get_sessionmaker()() as session:
        event = await session.get(Event, event_id)
        event.plan_excluded_steps = [{"code": "DEMAND_SURVEY", "reason": "예전 계획"}]
        await session.commit()

    plan = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)

    assert plan.status_code == 200, plan.text
    assert plan.json()["data"]["excludedSteps"][0]["name"] is None
    assert plan.json()["data"]["historyUsage"] is None
