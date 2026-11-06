"""본문 초안 응답 칸·「초안 다시 받기」·본문 수정 API (#334).

ActionOut의 contentStatus·contentSource·contentUnknowns·canRequestDraft, POST
/actions/{id}/draft, PATCH /actions/{id}의 content를 본다. AI는 가짜 함수로 바꾼다.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.ai as ai
from app.core.enums import ActionContentSource, ActionContentStatus, ActionStatus, ActionType, EventStatus
from app.models.events import Action
from app.services import action_draft_service
from tests.integration.event_seed import add_action, add_event, add_step, owner_with_club
from tests.integration.test_action_drafts import (  # noqa: F401  (fixture)
    _get,
    _set,
    app_db,
    spawned,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]


def _post(client: TestClient, headers: dict, path: str, body: dict | None = None):
    return client.post(f"/api/v1{path}", headers=headers, json=body or {})


def _action(client: TestClient, headers: dict, event_id: str, action_id: str) -> dict:
    rows = client.get(
        f"/api/v1/events/{event_id}/actions", headers=headers, params={"size": 100}
    ).json()["data"]
    return next(a for a in rows if a["id"] == action_id)


async def _notice(
    client: TestClient, *, event_status: EventStatus = EventStatus.ON_GOING, **values
) -> tuple[dict, str, str]:
    """(인증 헤더, eventId, actionId). values로 Action의 초안 상태를 직접 맞춘다."""
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=event_status, start_date=date(2026, 5, 10))
    step_id = await add_step(event_id, 1)
    action_id = await add_action(event_id, step_id=step_id, title="모집 공지 올리기")
    if values:
        await _set(Action, action_id, **values)
    return headers, event_id, action_id


AI_READY = {
    "content": "📢 봄 MT 모집\n신청 방법: [신청 링크]",
    "content_source": ActionContentSource.AI,
    "content_status": ActionContentStatus.READY,
    "content_unknowns": ["신청 링크"],
}


# --- 응답 칸 ----------------------------------------------------------------------


async def test_초안이_없으면_NONE이고_다시_받을_수_없다(client: TestClient, app_db: None) -> None:
    headers, event_id, action_id = await _notice(client)

    data = _action(client, headers, event_id, action_id)

    assert data["contentStatus"] == "NONE"
    assert data["contentSource"] is None
    assert data["contentUnknowns"] == []
    assert data["canRequestDraft"] is False


async def test_토리_초안은_비워_둔_곳과_함께_보이고_다시_받을_수_있다(
    client: TestClient, app_db: None
) -> None:
    headers, event_id, action_id = await _notice(client, **AI_READY)

    data = _action(client, headers, event_id, action_id)

    assert data["contentStatus"] == "READY"
    assert data["contentSource"] == "AI"
    assert data["contentUnknowns"] == ["신청 링크"]
    assert data["canRequestDraft"] is True


async def test_작성_중은_DRAFTING이고_3분이_지나면_FAILED로_보인다(
    client: TestClient, app_db: None
) -> None:
    headers, event_id, action_id = await _notice(
        client, content_status=ActionContentStatus.DRAFTING, draft_attempt_id="a1",
        draft_started_at=datetime.now(UTC),
    )
    fresh = _action(client, headers, event_id, action_id)
    assert (fresh["contentStatus"], fresh["canRequestDraft"]) == ("DRAFTING", False)

    await _set(Action, action_id, draft_started_at=datetime.now(UTC) - timedelta(minutes=4))

    stale = _action(client, headers, event_id, action_id)
    assert (stale["contentStatus"], stale["canRequestDraft"]) == ("FAILED", True)
    # 응답에서만 바꾼다. DB는 그대로 DRAFTING이다.
    assert (await _get(action_id)).content_status == ActionContentStatus.DRAFTING


async def test_실패한_초안은_FAILED이고_다시_받을_수_있다(client: TestClient, app_db: None) -> None:
    headers, event_id, action_id = await _notice(
        client, content_status=ActionContentStatus.FAILED, draft_error_code="AI_UNAVAILABLE"
    )

    data = _action(client, headers, event_id, action_id)

    assert (data["contentStatus"], data["canRequestDraft"]) == ("FAILED", True)


# --- 「초안 다시 받기」 -----------------------------------------------------------


async def test_다시_받기는_작성_중으로_바꾸고_version을_올린다(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, event_id, action_id = await _notice(client, **AI_READY)

    res = _post(client, headers, f"/actions/{action_id}/draft", {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["contentStatus"] == "DRAFTING"
    assert data["content"] is None
    assert data["contentSource"] is None
    assert data["contentUnknowns"] == []
    assert data["canRequestDraft"] is False
    assert data["version"] == 2
    assert [a for a, _ in spawned] == [action_id]
    assert (await _get(action_id)).draft_attempt_id == spawned[0][1]


async def test_3분_넘게_멈춘_작성은_다시_받을_수_있고_옛_작업의_결과는_버린다(
    client: TestClient, app_db: None, spawned: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def draft(request: ai.ActionDraftRequest) -> ai.ActionDraftResult:
        return ai.ActionDraftResult(content="새 초안 [장소]")

    monkeypatch.setattr("app.ai.draft_action_content", draft)
    headers, event_id, action_id = await _notice(
        client, content_status=ActionContentStatus.DRAFTING, draft_attempt_id="old",
        draft_started_at=datetime.now(UTC) - timedelta(minutes=4),
    )

    res = _post(client, headers, f"/actions/{action_id}/draft", {"expectedVersion": 1})
    assert res.status_code == 200, res.text
    new_attempt = spawned[0][1]

    # 서버 재시작 전에 띄운 옛 작업이 늦게 끝나도 저장하지 않는다.
    await action_draft_service._run_draft(action_id, "old")
    assert (await _get(action_id)).content is None
    assert _action(client, headers, event_id, action_id)["contentStatus"] == "DRAFTING"

    await action_draft_service._run_draft(action_id, new_attempt)
    data = _action(client, headers, event_id, action_id)
    assert (data["contentStatus"], data["content"], data["contentUnknowns"]) == (
        "READY", "새 초안 [장소]", ["장소"])
    assert data["version"] == 3


@pytest.mark.parametrize(
    "case",
    ["작성_중", "직접_고친_글", "승인됨", "초안_요청_전", "대상_종류_아님", "운영_중_아님"],
)
async def test_다시_받을_수_없는_상태면_409_DRAFT_NOT_ALLOWED(
    client: TestClient, app_db: None, spawned: list, case: str
) -> None:
    values = {
        "작성_중": {"content_status": ActionContentStatus.DRAFTING, "draft_started_at": datetime.now(UTC)},
        "직접_고친_글": {"content": "내가 쓴 공지", "content_source": ActionContentSource.USER,
                     "content_status": ActionContentStatus.READY},
        "승인됨": {**AI_READY, "status": ActionStatus.APPROVED},
        "초안_요청_전": {},
        "대상_종류_아님": {**AI_READY, "type": ActionType.TRANSFER},
        "운영_중_아님": AI_READY,
    }[case]
    event_status = EventStatus.PLANNING if case == "운영_중_아님" else EventStatus.ON_GOING
    headers, event_id, action_id = await _notice(client, event_status=event_status, **values)
    assert _action(client, headers, event_id, action_id)["canRequestDraft"] is False

    res = _post(client, headers, f"/actions/{action_id}/draft", {"expectedVersion": 1})

    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "DRAFT_NOT_ALLOWED"
    assert spawned == []
    # 운영진이 고친 글은 그대로 남는다.
    if case == "직접_고친_글":
        assert (await _get(action_id)).content == "내가 쓴 공지"


async def test_본_뒤에_바뀐_Action은_409_VERSION_CONFLICT(
    client: TestClient, app_db: None, spawned: list
) -> None:
    headers, _event_id, action_id = await _notice(client, **AI_READY, version=2)

    res = _post(client, headers, f"/actions/{action_id}/draft", {"expectedVersion": 1})

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"
    assert spawned == []


async def test_없는_Action은_404이고_다른_동아리는_403(client: TestClient, app_db: None) -> None:
    headers, _event_id, action_id = await _notice(client, **AI_READY)
    other_headers, _ = owner_with_club(client, "other-owner")

    missing = _post(client, headers, "/actions/act_없는행동/draft", {"expectedVersion": 1})
    forbidden = _post(client, other_headers, f"/actions/{action_id}/draft", {"expectedVersion": 1})

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ACTION_NOT_FOUND"
    assert forbidden.status_code == 403


# --- 본문 수정 --------------------------------------------------------------------


async def test_승인된_토리_초안을_고치면_운영진_글이_되고_다시_승인을_받는다(
    client: TestClient, app_db: None
) -> None:
    headers, event_id, action_id = await _notice(client, **AI_READY)
    approve = _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})
    assert approve.status_code == 200, approve.text

    res = client.patch(
        f"/api/v1/actions/{action_id}", headers=headers,
        json={"expectedVersion": 2, "content": "📢 봄 MT 모집\n신청 방법: https://forms.example"},
    )

    assert res.status_code == 200, res.text
    # 응답 모양은 기존 PlannedStepOut 그대로다.
    assert "actions" in res.json()["data"]
    data = _action(client, headers, event_id, action_id)
    assert data["content"] == "📢 봄 MT 모집\n신청 방법: https://forms.example"
    assert data["status"] == "PENDING"
    assert data["contentSource"] == "USER"
    assert data["contentStatus"] == "READY"
    assert data["contentUnknowns"] == []
    assert data["canRequestDraft"] is False
    assert data["version"] == 3


@pytest.mark.parametrize("content", ["", "   ", None])
async def test_본문을_비우면_422(client: TestClient, app_db: None, content: str | None) -> None:
    headers, event_id, action_id = await _notice(client, **AI_READY)

    res = client.patch(f"/api/v1/actions/{action_id}", headers=headers,
                       json={"expectedVersion": 1, "content": content})

    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_FAILED"
    assert "content" in res.json()["error"]["fields"]
    assert _action(client, headers, event_id, action_id)["contentSource"] == "AI"


async def test_본문을_보내지_않으면_초안_상태는_그대로다(client: TestClient, app_db: None) -> None:
    headers, event_id, action_id = await _notice(client, **AI_READY)

    res = client.patch(f"/api/v1/actions/{action_id}", headers=headers,
                       json={"expectedVersion": 1, "title": "모집 공지 다시 올리기"})

    assert res.status_code == 200, res.text
    data = _action(client, headers, event_id, action_id)
    assert (data["contentSource"], data["contentUnknowns"]) == ("AI", ["신청 링크"])
