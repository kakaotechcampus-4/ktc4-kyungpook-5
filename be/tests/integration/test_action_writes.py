"""행동 처리·단계 완료 API 테스트 (#41).

승인·거절·확인 요청 응답·실행 완료는 상태와 version(낙관적 잠금)을 함께 확인한다.
행동이 모두 DONE이 되면 단계가 자동으로 완료되는지도 본다.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.enums import ActionStatus, ActionType, EventStatus, MemberRole
from app.db import session as db_session
from app.models.clubs import Member
from app.models.events import Step
from app.services import action_service
from app.services.action_service import AlreadyResolved
from tests.integration.event_seed import (
    add_action,
    add_event,
    add_step,
    member_of,
    owner_with_club,
)

pytestmark = [pytest.mark.db, pytest.mark.anyio]

CONFIRM_PAYLOAD = {
    "options": [
        {"key": "CHANGE_B", "label": "B펜션으로 변경"},
        {"key": "KEEP_A", "label": "A펜션 대기"},
    ],
    "allow_manual": True,
}


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


def _post(client: TestClient, headers: dict, path: str, body: dict | None = None):
    return client.post(f"/api/v1{path}", headers=headers, json=body or {})


def _action(client: TestClient, headers: dict, event_id: str, action_id: str) -> dict:
    rows = client.get(
        f"/api/v1/events/{event_id}/actions", headers=headers, params={"size": 100}
    ).json()["data"]
    return next(a for a in rows if a["id"] == action_id)


def _steps(client: TestClient, headers: dict, event_id: str) -> list[dict]:
    return client.get(f"/api/v1/events/{event_id}/steps", headers=headers).json()["data"]


# --- 승인·거절 ----------------------------------------------------------------


async def test_승인하면_처리자와_시각이_남고_version이_오른다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id, type=ActionType.TRANSFER)

    res = _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "APPROVED"
    assert data["resolvedBy"]["role"] == "OWNER"
    assert data["resolvedAt"] is not None
    assert data["version"] == 2
    assert data["canApprove"] is False
    # 조회에도 같은 결과가 보인다.
    assert _action(client, headers, event_id, action_id)["status"] == "APPROVED"


async def test_거절하면_사유가_남는다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id, type=ActionType.CONTRACT)

    res = _post(
        client, headers, f"/actions/{action_id}/deny",
        {"expectedVersion": 1, "reason": "  견적이 너무 높아요  "},
    )

    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "DENIED"
    assert res.json()["data"]["denyReason"] == "견적이 너무 높아요"


async def test_이미_처리된_행동은_409_ALREADY_RESOLVED(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id)
    _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})

    # 처리 후 받은 최신 version으로 보내도 이미 처리된 행동은 다시 처리하지 않는다.
    again = _post(client, headers, f"/actions/{action_id}/deny", {"expectedVersion": 2})

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_RESOLVED"


async def test_본_뒤에_내용이_바뀐_대기_행동은_409_VERSION_CONFLICT(
    client: TestClient, app_db: None
) -> None:
    """#106으로 내용을 고치면 version이 오른다. 본 적 없는 내용을 승인하지 않는다."""
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id)
    async with db_session.get_sessionmaker()() as session:
        from app.models.events import Action

        action = await session.get(Action, action_id)
        action.content = "다른 운영진이 고친 문구"
        action.version = 2
        await session.commit()

    res = _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"
    assert _action(client, headers, event_id, action_id)["status"] == "PENDING"


async def test_확인_요청은_승인_거절이_아니라_resolve로만_처리한다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    confirm_id = await add_action(
        event_id, type=ActionType.CONFIRMATION, approve_needed=False, payload=CONFIRM_PAYLOAD
    )
    notice_id = await add_action(event_id)

    approve = _post(client, headers, f"/actions/{confirm_id}/approve", {"expectedVersion": 1})
    resolve = _post(
        client, headers, f"/actions/{notice_id}/resolve",
        {"expectedVersion": 1, "choice": "CHANGE_B"},
    )

    assert approve.status_code == 422
    assert resolve.status_code == 422


async def test_권한과_존재_여부(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id)
    member_headers = await member_of(client, club_id, MemberRole.MEMBER, "member")
    other_headers, _other_club = owner_with_club(client, "other-owner")
    body = {"expectedVersion": 1}

    assert client.post(f"/api/v1/actions/{action_id}/approve", json=body).status_code == 401
    assert _post(client, member_headers, f"/actions/{action_id}/approve", body).status_code == 403
    assert _post(client, other_headers, f"/actions/{action_id}/approve", body).status_code == 403
    missing = _post(client, headers, "/actions/act_없는행동/approve", body)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ACTION_NOT_FOUND"
    assert _post(client, headers, f"/actions/{action_id}/approve", {}).status_code == 422


async def test_운영진도_승인할_수_있다(client: TestClient, app_db: None) -> None:
    _headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id)
    manager_headers = await member_of(client, club_id, MemberRole.MANAGER, "manager")

    res = _post(client, manager_headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    assert res.json()["data"]["resolvedBy"]["role"] == "MANAGER"


async def test_두_운영진이_동시에_승인하면_한_명만_처리된다(
    client: TestClient, app_db: None
) -> None:
    """먼저 승인한 쪽이 행을 잠근 채 커밋 전이면, 늦은 승인은 잠금에서 기다렸다가
    상태를 다시 보고 ALREADY_RESOLVED가 된다."""
    from sqlalchemy import select

    from app.models.events import Action

    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(event_id)
    sessionmaker = db_session.get_sessionmaker()
    async with sessionmaker() as session:
        member = await session.scalar(select(Member).where(Member.club_id == club_id))

    async with sessionmaker() as first, sessionmaker() as second:
        locked = await first.scalar(select(Action).where(Action.id == action_id).with_for_update())
        racing = asyncio.create_task(
            action_service.approve(second, action_id=action_id, member=member, expected_version=1)
        )
        await asyncio.sleep(0.3)
        assert not racing.done()  # 첫 승인의 행 잠금에서 기다리는 중
        locked.status = ActionStatus.APPROVED
        locked.version += 1
        await first.commit()

        with pytest.raises(AlreadyResolved):
            await racing


# --- 확인 요청 응답 -------------------------------------------------------------


async def test_확인_요청에_선택지로_답하면_DONE이고_고른_답이_남는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    action_id = await add_action(
        event_id, type=ActionType.CONFIRMATION, approve_needed=False, payload=CONFIRM_PAYLOAD
    )

    res = _post(
        client, headers, f"/actions/{action_id}/resolve",
        {"expectedVersion": 1, "choice": "CHANGE_B"},
    )

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["status"] == "DONE"
    assert data["resolvedChoice"] == "CHANGE_B"
    assert data["manualValue"] is None
    # 선택지는 그대로 남는다.
    assert [o["key"] for o in data["options"]] == ["CHANGE_B", "KEEP_A"]


async def test_직접_처리는_허용된_요청에만_내용과_함께(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    manual_ok = await add_action(
        event_id, type=ActionType.CONFIRMATION, approve_needed=False, payload=CONFIRM_PAYLOAD
    )
    manual_off = await add_action(
        event_id, type=ActionType.CONFIRMATION, approve_needed=False,
        payload={**CONFIRM_PAYLOAD, "allow_manual": False},
    )

    empty = _post(client, headers, f"/actions/{manual_ok}/resolve",
                  {"expectedVersion": 1, "choice": "MANUAL", "manualValue": "  "})
    not_allowed = _post(client, headers, f"/actions/{manual_off}/resolve",
                        {"expectedVersion": 1, "choice": "MANUAL", "manualValue": "C펜션"})
    unknown = _post(client, headers, f"/actions/{manual_off}/resolve",
                    {"expectedVersion": 1, "choice": "NOPE"})
    ok = _post(client, headers, f"/actions/{manual_ok}/resolve",
               {"expectedVersion": 1, "choice": "MANUAL", "manualValue": "C펜션으로 직접 예약"})

    assert empty.status_code == 422
    assert not_allowed.status_code == 422
    assert unknown.status_code == 422
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["resolvedChoice"] == "MANUAL"
    assert ok.json()["data"]["manualValue"] == "C펜션으로 직접 예약"


# --- 실행 완료와 단계 자동 완료 --------------------------------------------------


async def test_승인된_행동을_실행_완료로_기록하면_DONE(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10)
    action_id = await add_action(event_id, step_id=step_id)

    before = _post(client, headers, f"/actions/{action_id}/done", {"expectedVersion": 1})
    _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})
    done = _post(client, headers, f"/actions/{action_id}/done", {"expectedVersion": 2})

    # 승인 전에는 실행 완료를 남길 수 없다.
    assert before.status_code == 409
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "DONE"
    assert done.json()["data"]["resolvedBy"]["role"] == "OWNER"


async def test_단계의_마지막_행동이_끝나면_단계가_자동_완료된다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10)
    await add_step(event_id, 20)
    first = await add_action(event_id, step_id=step_id, status=ActionStatus.APPROVED)
    second = await add_action(event_id, step_id=step_id, status=ActionStatus.APPROVED)

    _post(client, headers, f"/actions/{first}/done", {"expectedVersion": 1})
    after_first = _steps(client, headers, event_id)
    _post(client, headers, f"/actions/{second}/done", {"expectedVersion": 1})
    after_second = _steps(client, headers, event_id)

    assert after_first[0]["state"] == "CURRENT"
    assert after_first[0]["completedAt"] is None
    assert after_second[0]["state"] == "DONE"
    assert after_second[0]["completedAt"] is not None
    assert after_second[1]["state"] == "CURRENT"
    async with db_session.get_sessionmaker()() as session:
        step = await session.get(Step, step_id)
        assert step.completed_by is None


async def test_거절된_행동이_남아_있으면_단계를_자동_완료하지_않는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10)
    await add_action(event_id, step_id=step_id, status=ActionStatus.DENIED)
    action_id = await add_action(event_id, step_id=step_id, status=ActionStatus.APPROVED)

    _post(client, headers, f"/actions/{action_id}/done", {"expectedVersion": 1})

    assert _steps(client, headers, event_id)[0]["completedAt"] is None


# --- 단계 완료 -------------------------------------------------------------------


async def test_단계를_직접_완료하면_남은_행동_수를_알려_준다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10)
    await add_action(event_id, step_id=step_id)
    await add_action(event_id, step_id=step_id, status=ActionStatus.APPROVED)
    await add_action(event_id, step_id=step_id, status=ActionStatus.DONE)

    res = _post(client, headers, f"/steps/{step_id}/complete")
    again = _post(client, headers, f"/steps/{step_id}/complete")

    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["id"] == step_id
    assert data["completedAt"] is not None
    assert data["completedBy"]["role"] == "OWNER"
    assert data["pendingActionCount"] == 2
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "STEP_ALREADY_COMPLETED"


async def test_행동이_없는_수동_단계도_완료할_수_있다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    step_id = await add_step(event_id, 10)
    member_headers = await member_of(client, club_id, MemberRole.MEMBER, "member")

    assert _post(client, member_headers, f"/steps/{step_id}/complete").status_code == 403
    res = _post(client, headers, f"/steps/{step_id}/complete")
    missing = _post(client, headers, "/steps/stp_없는단계/complete")

    assert res.status_code == 200, res.text
    assert res.json()["data"]["pendingActionCount"] == 0
    assert _steps(client, headers, event_id)[0]["state"] == "DONE"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "STEP_NOT_FOUND"


# --- 운영 중에만 처리, 계획 확정 (#177, FE 명세 v1 :confirm) ------------------------


async def test_계획_중인_행사는_처리를_받지_않고_canApprove도_false(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.PLANNING)
    step_id = await add_step(event_id, 10)
    action_id = await add_action(event_id, step_id=step_id)

    approve = _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})
    complete = _post(client, headers, f"/steps/{step_id}/complete")

    assert approve.status_code == 409
    assert approve.json()["error"]["code"] == "EVENT_NOT_ON_GOING"
    assert complete.status_code == 409
    assert _action(client, headers, event_id, action_id)["canApprove"] is False


async def test_canApprove는_실제로_승인할_수_있는_행동에만_true(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)
    needs = await add_action(event_id, type=ActionType.TRANSFER)
    no_approval = await add_action(event_id, approve_needed=False)
    confirm = await add_action(
        event_id, type=ActionType.CONFIRMATION, approve_needed=False, payload=CONFIRM_PAYLOAD
    )

    assert _action(client, headers, event_id, needs)["canApprove"] is True
    # 승인이 필요 없는 행동은 /approve가 422라 버튼을 보이지 않는다.
    assert _action(client, headers, event_id, no_approval)["canApprove"] is False
    # 확인 요청은 /resolve로 답할 수 있다.
    assert _action(client, headers, event_id, confirm)["canApprove"] is True


async def test_계획을_확정하면_운영이_시작되고_처리를_받는다(
    client: TestClient, app_db: None
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(
        club_id, status=EventStatus.PLANNING, title="봄 MT", start_date=date(2027, 3, 20)
    )
    step_id = await add_step(event_id, 10)
    action_id = await add_action(event_id, step_id=step_id)

    res = _post(client, headers, f"/events/{event_id}:confirm")
    again = _post(client, headers, f"/events/{event_id}:confirm")
    approve = _post(client, headers, f"/actions/{action_id}/approve", {"expectedVersion": 1})

    assert res.status_code == 200, res.text
    assert res.json()["data"] == {
        "id": event_id, "status": "ON_GOING", "title": "봄 MT", "startDate": "2027-03-20"
    }
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "EVENT_NOT_PLANNING"
    assert approve.status_code == 200, approve.text
    assert _steps(client, headers, event_id)[0]["state"] == "CURRENT"


async def test_시작일이나_단계가_없으면_확정할_수_없다(client: TestClient, app_db: None) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.PLANNING)
    member_headers = await member_of(client, club_id, MemberRole.MEMBER, "member")

    res = _post(client, headers, f"/events/{event_id}:confirm")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PLAN_INCOMPLETE"
    assert set(res.json()["error"]["fields"]) == {"startDate", "steps"}
    assert _post(client, member_headers, f"/events/{event_id}:confirm").status_code == 403


async def test_확정된_행사는_계획_대화와_생성을_받지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id)  # ON_GOING

    async def must_not_call(request, **_):
        raise AssertionError("확정된 행사에서 AI를 부르면 안 된다")

    monkeypatch.setattr("app.ai.chat_planning", must_not_call)
    monkeypatch.setattr("app.ai.generate_planning_preview", must_not_call)

    chat = _post(client, headers, f"/events/{event_id}/plan/chat",
                 {"messageId": "m1", "message": "MT", "baseRevision": 0})
    generate = _post(client, headers, f"/events/{event_id}/plan/generate", {"baseRevision": 0})

    assert chat.status_code == 409
    assert chat.json()["error"]["code"] == "EVENT_NOT_PLANNING"
    assert generate.status_code == 409


async def test_생성_중에_확정되면_처리_기록을_지우지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """생성은 수십 초 걸린다. 그사이 확정·승인된 행사는 생성 결과로 덮어쓰지 않는다."""
    from tests.integration.test_events_planning import _fake_generation_result

    headers, club_id = owner_with_club(client)
    event_id = await add_event(club_id, status=EventStatus.PLANNING)
    step_id = await add_step(event_id, 10)
    action_id = await add_action(event_id, step_id=step_id)

    async def confirm_while_generating(request):
        async with db_session.get_sessionmaker()() as session:
            from app.models.events import Action, Event

            (await session.get(Event, event_id)).status = EventStatus.ON_GOING
            approved = await session.get(Action, action_id)
            approved.status = ActionStatus.APPROVED
            await session.commit()
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", confirm_while_generating)

    res = _post(client, headers, f"/events/{event_id}/plan/generate", {"baseRevision": 0})

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EVENT_NOT_PLANNING"
    assert _action(client, headers, event_id, action_id)["status"] == "APPROVED"


async def test_대화_중에_확정되면_운영_중_행사의_조건을_바꾸지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """대화도 수 초~수십 초 걸린다. 그사이 확정된 행사에 대화 결과(조건)를 저장하지 않는다."""
    from tests.integration.test_events_planning import _fake_chat_result

    headers, club_id = owner_with_club(client)
    event_id = await add_event(
        club_id, status=EventStatus.PLANNING, location="가평", expected_headcount=30
    )

    async def confirm_while_chatting(request, *, records=None):
        async with db_session.get_sessionmaker()() as session:
            from app.models.events import Event

            (await session.get(Event, event_id)).status = EventStatus.ON_GOING
            await session.commit()
        return _fake_chat_result(event_type="MT", headcount=99)

    monkeypatch.setattr("app.ai.chat_planning", confirm_while_chatting)

    res = _post(client, headers, f"/events/{event_id}/plan/chat",
                {"messageId": "m1", "message": "인원 99명으로", "baseRevision": 0})
    detail = client.get(f"/api/v1/events/{event_id}", headers=headers).json()["data"]

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EVENT_NOT_PLANNING"
    assert detail["headcount"] == 30
    assert detail["location"] == "가평"
