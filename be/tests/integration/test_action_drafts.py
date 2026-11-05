"""운영 중 공지·발송 Action의 본문 초안: 신호·뒤에서 도는 작업·저장 조건 (#334).

AI(app.ai.draft_action_content)는 가짜 함수로 바꾼다. 작업을 띄우는 함수(spawn_draft)는
띄운 (actionId, attemptId)를 기록만 하게 바꾸고, 테스트가 _run_draft를 직접 기다린다.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

import app.ai as ai
from app.core.enums import (
    ActionContentSource,
    ActionContentStatus,
    ActionStatus,
    ActionType,
    EventStatus,
    StepCode,
)
from app.db import session as db_session
from app.main import app
from app.models.events import Action, Event, Step
from app.services import action_draft_service, event_service
from app.services.action_draft_service import spawn_draft as REAL_SPAWN
from tests.integration.event_seed import (
    PASSWORD,
    add_action,
    add_event,
    add_step,
    owner_with_club,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]

DRAFT = "📢 봄 MT 참가자 모집\n5월 10일(토)~11일(일) 가평으로 MT를 갑니다!\n신청 방법: [신청 링크]"


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """띄운 초안 작업을 기록만 한다. 테스트가 _run_draft로 직접 실행한다."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        action_draft_service, "spawn_draft", lambda action_id, attempt_id: calls.append((action_id, attempt_id))
    )
    return calls


def fake_ai(monkeypatch: pytest.MonkeyPatch, *, content: str = DRAFT, error: Exception | None = None):
    requests: list[ai.ActionDraftRequest] = []

    async def draft_action_content(request: ai.ActionDraftRequest) -> ai.ActionDraftResult:
        requests.append(request)
        if error is not None:
            raise error
        return ai.ActionDraftResult(content=content)

    monkeypatch.setattr("app.ai.draft_action_content", draft_action_content)
    return requests


async def _get(action_id: str) -> Action:
    async with db_session.get_sessionmaker()() as session:
        return await session.get(Action, action_id)


async def _set(model, row_id: str, **values) -> None:
    async with db_session.get_sessionmaker()() as session:
        await session.execute(update(model).where(model.id == row_id).values(**values))
        await session.commit()


def _post(client: TestClient, headers: dict, path: str, body: dict | None = None):
    return client.post(f"/api/v1{path}", headers=headers, json=body or {})


async def _operating_event(club_id: str, *, status: EventStatus = EventStatus.ON_GOING) -> dict:
    """단계 1(모집 공지)·단계 2(사전 안내)를 가진 행사와 Action id들."""
    event_id = await add_event(
        club_id, status=status, start_date=date(2026, 5, 10), end_date=date(2026, 5, 11),
        location="가평", expected_headcount=40,
    )
    step1 = await add_step(event_id, 1, name="모집 공지", code=StepCode.RECRUIT_NOTICE)
    step2 = await add_step(event_id, 2, name="사전 안내", code=StepCode.PRE_EVENT_NOTICE)
    ids = {
        "event": event_id,
        "step1": step1,
        "step2": step2,
        "notice": await add_action(event_id, step_id=step1, title="모집 공지 올리기"),
        "send": await add_action(event_id, step_id=step1, title="신청서 보내기", type=ActionType.EXTERNAL_SEND),
        "transfer": await add_action(event_id, step_id=step1, title="계약금 보내기", type=ActionType.TRANSFER),
        "written": await add_action(event_id, step_id=step1, title="이미 쓴 공지", content="직접 쓴 공지"),
        "next_notice": await add_action(event_id, step_id=step2, title="사전 안내 공지"),
    }
    return ids


# --- 신호 ------------------------------------------------------------------------


async def test_행사를_시작하면_첫_단계의_빈_공지_발송만_작성_중이_된다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, club_id = owner_with_club(client)
    ids = await _operating_event(club_id, status=EventStatus.PLANNING)
    # 첫 단계가 되기 전에 미리 승인한 공지. 승인한 내용을 바꾸지 않도록 초안 대상이 아니다.
    approved = await add_action(ids["event"], step_id=ids["step1"], title="미리 승인한 공지",
                                status=ActionStatus.APPROVED)

    res = _post(client, headers, f"/events/{ids['event']}/start")

    assert res.status_code == 200, res.text
    drafting = {key for key in ("notice", "send", "transfer", "written", "next_notice")
                if (await _get(ids[key])).content_status == ActionContentStatus.DRAFTING}
    assert drafting == {"notice", "send"}
    assert (await _get(approved)).content_status == ActionContentStatus.NONE
    assert {action_id for action_id, _ in spawned} == {ids["notice"], ids["send"]}
    notice = await _get(ids["notice"])
    assert notice.draft_attempt_id and notice.draft_started_at is not None
    # 작성 중 표시만으로는 version을 올리지 않는다 — 그사이 승인해도 된다.
    assert notice.version == 1


async def test_계획_중인_행사는_초안을_요청하지_않는다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    _headers, club_id = owner_with_club(client)
    ids = await _operating_event(club_id, status=EventStatus.PLANNING)

    await action_draft_service.request_current_step_drafts(ids["event"])

    assert (await _get(ids["notice"])).content_status == ActionContentStatus.NONE
    assert spawned == []


async def test_단계를_직접_완료하면_다음_단계의_공지가_작성_중이_된다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, club_id = owner_with_club(client)
    ids = await _operating_event(club_id)
    # 다음 단계에 미리 승인한 공지가 있어도 현재 단계가 됐을 때 초안을 쓰지 않는다.
    pre_approved = await add_action(ids["event"], step_id=ids["step2"], title="미리 승인",
                                    status=ActionStatus.APPROVED)

    res = _post(client, headers, f"/steps/{ids['step1']}/complete")

    assert res.status_code == 200, res.text
    assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.DRAFTING
    assert (await _get(pre_approved)).content_status == ActionContentStatus.NONE
    # 끝난 단계의 공지는 더 이상 현재 단계가 아니라 그대로다.
    assert (await _get(ids["notice"])).content_status == ActionContentStatus.NONE
    assert [action_id for action_id, _ in spawned] == [ids["next_notice"]]


async def test_완료_표시로_단계가_자동_완료되면_다음_단계가_작성_중이_된다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, start_date=date(2026, 5, 10))
    step1 = await add_step(event_id, 1)
    step2 = await add_step(event_id, 2, code=StepCode.RECRUIT_NOTICE)
    only = await add_action(event_id, step_id=step1, type=ActionType.EXPENSE, approve_needed=False)
    notice = await add_action(event_id, step_id=step2)

    res = _post(client, headers, f"/actions/{only}/done", {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    assert (await _get(notice)).content_status == ActionContentStatus.DRAFTING
    assert [action_id for action_id, _ in spawned] == [notice]


async def test_확인_요청_답변으로_단계가_자동_완료되면_다음_단계가_작성_중이_된다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, start_date=date(2026, 5, 10))
    step1 = await add_step(event_id, 1)
    step2 = await add_step(event_id, 2, code=StepCode.RECRUIT_NOTICE)
    confirm = await add_action(
        event_id, step_id=step1, type=ActionType.CONFIRMATION, approve_needed=False,
        payload={"options": [{"key": "OK", "label": "좋아요"}], "allow_manual": False},
    )
    notice = await add_action(event_id, step_id=step2)

    res = _post(client, headers, f"/actions/{confirm}/resolve", {"expectedVersion": 1, "choice": "OK"})

    assert res.status_code == 200, res.text
    assert (await _get(notice)).content_status == ActionContentStatus.DRAFTING


async def test_작업을_띄우다_실패해도_단계_완료는_성공한다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client)
    ids = await _operating_event(club_id)

    def broken(action_id: str, attempt_id: str) -> None:
        raise RuntimeError("작업을 띄울 수 없음")

    monkeypatch.setattr(action_draft_service, "spawn_draft", broken)

    res = _post(client, headers, f"/steps/{ids['step1']}/complete")

    assert res.status_code == 200, res.text
    # DRAFTING으로 남은 것은 3분 뒤 응답에서 FAILED로 보이고 「다시 받기」로 복구한다.
    assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.DRAFTING


# --- 뒤에서 도는 작업 -----------------------------------------------------------


async def _start_draft(client: TestClient, ids: dict, spawned: list) -> str:
    """단계 1을 완료해 단계 2의 공지를 작성 중으로 만들고 그 시도 id를 돌려준다."""
    headers = ids["headers"]
    assert _post(client, headers, f"/steps/{ids['step1']}/complete").status_code == 200
    return dict(spawned)[ids["next_notice"]]


async def _ids(client: TestClient) -> dict:
    headers, club_id = owner_with_club(client)
    return {**await _operating_event(club_id), "headers": headers}


async def test_초안이_오면_본문과_비워_둔_곳을_저장하고_version을_올린다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = fake_ai(monkeypatch)
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    action = await _get(ids["next_notice"])
    assert action.content == DRAFT
    assert action.content_status == ActionContentStatus.READY
    assert action.content_source == ActionContentSource.AI
    assert action.content_unknowns == ["신청 링크"]
    assert action.version == 2
    request = requests[0]
    assert request.club_name.endswith("동아리")
    assert request.event.start_date == date(2026, 5, 10)
    assert request.event.location == "가평"
    assert request.step.code == StepCode.PRE_EVENT_NOTICE
    assert request.action.type == ActionType.NOTICE
    assert request.today == event_service.today_kst()


async def test_단계_날짜는_한국_시간_날짜로_넘긴다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests = fake_ai(monkeypatch)
    ids = await _ids(client)
    await _set(Step, ids["step2"],
               starts_at=datetime(2026, 4, 19, 16, 0, tzinfo=UTC),
               deadline=datetime(2026, 4, 30, 15, 0, tzinfo=UTC))
    attempt = await _start_draft(client, ids, spawned)

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    # 2026-04-30T15:00:00Z는 한국 시간으로 5월 1일 0시다.
    assert requests[0].step.deadline == date(2026, 5, 1)
    assert requests[0].step.starts_on == date(2026, 4, 20)


async def test_그사이_승인된_Action에는_초안을_저장하지_않는다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ai(monkeypatch)
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)
    approve = _post(client, ids["headers"], f"/actions/{ids['next_notice']}/approve", {"expectedVersion": 1})
    assert approve.status_code == 200, approve.text

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    action = await _get(ids["next_notice"])
    assert action.content is None
    assert action.status == ActionStatus.APPROVED
    assert action.version == 2
    # 승인된 카드가 3분 뒤 "실패"로 보이지 않게 작성 중 표시를 걷어 낸다.
    assert action.content_status == ActionContentStatus.NONE


async def test_운영진이_고친_본문은_덮어쓰지_않는다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ai(monkeypatch)
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)
    # 본문 수정 API(PATCH)가 남기는 모양. API 자체는 test_action_draft_api에서 본다.
    await _set(Action, ids["next_notice"], content="내가 쓴 사전 안내", version=2,
               content_source=ActionContentSource.USER, content_status=ActionContentStatus.READY)

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    action = await _get(ids["next_notice"])
    assert action.content == "내가 쓴 사전 안내"
    assert action.content_source == ActionContentSource.USER
    assert action.content_status == ActionContentStatus.READY
    assert action.version == 2


async def test_더_새_시도가_시작되면_옛_결과를_버린다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ai(monkeypatch)
    ids = await _ids(client)
    old = await _start_draft(client, ids, spawned)
    # 「다시 받기」가 새 시도를 시작한 상태. API 흐름은 test_action_draft_api에서 본다.
    new = "newer-attempt"
    await _set(Action, ids["next_notice"], draft_attempt_id=new)

    await action_draft_service._run_draft(ids["next_notice"], old)

    action = await _get(ids["next_notice"])
    assert action.content is None
    assert action.content_status == ActionContentStatus.DRAFTING
    assert action.draft_attempt_id == new

    await action_draft_service._run_draft(ids["next_notice"], new)
    assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.READY


async def test_행사가_취소되면_초안을_저장하지_않는다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ai(monkeypatch)
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)
    cancel = _post(client, ids["headers"], f"/events/{ids['event']}/cancel")
    assert cancel.status_code == 200, cancel.text

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    action = await _get(ids["next_notice"])
    assert action.content is None
    assert action.content_status == ActionContentStatus.NONE


@pytest.mark.parametrize(
    ("error", "code"),
    [
        # AIInvalidResponseError는 AIRetryableError의 하위 타입이다 — 먼저 구분해야 한다.
        (ai.AIInvalidResponseError("검사를 통과하지 못함"), "AI_INVALID_RESPONSE"),
        (ai.AITimeoutError("시간 초과"), "AI_UNAVAILABLE"),
        (ai.AIRetryableError("모델 오류"), "AI_UNAVAILABLE"),
        (NotImplementedError("구현 전"), "INTERNAL_ERROR"),
        (RuntimeError("버그"), "INTERNAL_ERROR"),
    ],
)
async def test_AI가_실패하면_FAILED와_오류_코드를_남긴다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch,
    error: Exception, code: str,
) -> None:
    fake_ai(monkeypatch, error=error)
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    action = await _get(ids["next_notice"])
    assert action.content_status == ActionContentStatus.FAILED
    assert action.draft_error_code == code
    assert action.content is None
    assert action.version == 1


async def test_구현_전_AI_함수도_FAILED로_남는다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    # 가짜로 바꾸지 않은 ai.draft_action_content는 #333 구현 전 NotImplementedError를 낸다.
    ids = await _ids(client)
    attempt = await _start_draft(client, ids, spawned)

    await action_draft_service._run_draft(ids["next_notice"], attempt)

    assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.FAILED


# --- 응답은 AI를 기다리지 않는다 ---------------------------------------------------


async def test_행사_시작과_단계_완료_응답은_AI를_기다리지_않는다(
    app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # TestClient는 요청이 끝나면 이벤트 루프를 닫으므로, 같은 루프에서 ASGI 앱을 불러
    # 실제 asyncio 작업으로 띄운다. 가짜 AI는 release가 열릴 때까지 멈춰 있다.
    monkeypatch.setattr(action_draft_service, "spawn_draft", REAL_SPAWN)
    release = asyncio.Event()

    async def blocked(request: ai.ActionDraftRequest) -> ai.ActionDraftResult:
        await release.wait()
        return ai.ActionDraftResult(content=f"{request.action.title} [신청 링크]")

    monkeypatch.setattr("app.ai.draft_action_content", blocked)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        email = f"draft-wait-{id(release)}@example.com"
        await http.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "초안"})
        token = (await http.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
                 ).json()["data"]["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}
        club_id = (await http.post("/api/v1/clubs", headers=headers, json={"name": "초안 동아리"})
                   ).json()["data"]["id"]
        ids = await _operating_event(club_id, status=EventStatus.PLANNING)

        start = await asyncio.wait_for(http.post(f"/api/v1/events/{ids['event']}/start", headers=headers), 5)
        assert start.status_code == 200, start.text
        assert (await _get(ids["notice"])).content_status == ActionContentStatus.DRAFTING

        complete = await asyncio.wait_for(
            http.post(f"/api/v1/steps/{ids['step1']}/complete", headers=headers), 5)
        assert complete.status_code == 200, complete.text
        assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.DRAFTING
        # AI가 아직 멈춰 있어 작업이 남아 있다.
        assert len(action_draft_service._running) == 3

        release.set()
        await asyncio.wait_for(asyncio.gather(*action_draft_service._running), 5)

    assert not action_draft_service._running
    assert (await _get(ids["notice"])).content == "모집 공지 올리기 [신청 링크]"
    assert (await _get(ids["next_notice"])).content_status == ActionContentStatus.READY
