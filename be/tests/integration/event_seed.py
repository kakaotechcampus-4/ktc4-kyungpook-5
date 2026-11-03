"""행사·단계·행동 API 테스트가 함께 쓰는 준비 함수 (#41).

계정·동아리는 실제 API로 만들고, 행사·단계·행동은 아직 만드는 쓰기 API가 없거나
(승인·완료 등) AI 호출이 필요해(계획 생성) DB에 바로 넣는다.
"""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    MemberRole,
    MemberStatus,
    StepActor,
    StepCode,
    StepPhase,
)
from app.db import session as db_session
from app.models.clubs import Member
from app.models.events import Action, Event, Step

PASSWORD = "PmTest-2027!"


def signup_and_login(client: TestClient, tag: str) -> tuple[str, dict]:
    """새 계정을 만들고 (accountId, 인증 헤더)를 돌려준다."""
    email = f"{tag}-{uuid.uuid4().hex[:12]}@example.com"
    signup = client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": tag}
    )
    assert signup.status_code == 201, signup.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['data']['accessToken']}"}
    return signup.json()["data"]["id"], headers


def owner_with_club(client: TestClient, tag: str = "event-owner") -> tuple[dict, str]:
    """동아리를 만든 대표의 (인증 헤더, clubId)."""
    _account_id, headers = signup_and_login(client, tag)
    club = client.post("/api/v1/clubs", headers=headers, json={"name": f"{tag} 동아리"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


async def member_of(
    client: TestClient, club_id: str, role: MemberRole, tag: str = "event-member"
) -> dict:
    """club_id에 role로 들어간 새 동아리원의 인증 헤더. 초대·수락 절차는 건너뛴다."""
    account_id, headers = signup_and_login(client, tag)
    async with db_session.get_sessionmaker()() as session:
        session.add(
            Member(
                club_id=club_id,
                account_id=account_id,
                name=tag,
                role=role,
                status=MemberStatus.ACTIVE,
            )
        )
        await session.commit()
    return headers


async def _insert(row: Any) -> str:
    async with db_session.get_sessionmaker()() as session:
        session.add(row)
        await session.commit()
        return row.id


async def add_event(
    club_id: str,
    *,
    title: str = "봄 MT",
    status: EventStatus = EventStatus.ON_GOING,
    start_date: date | None = None,
    end_date: date | None = None,
    location: str | None = None,
    expected_headcount: int | None = None,
) -> str:
    return await _insert(
        Event(
            club_id=club_id,
            title=title,
            status=status,
            start_date=start_date,
            end_date=end_date,
            location=location,
            expected_headcount=expected_headcount,
        )
    )


async def add_step(
    event_id: str,
    step_order: int,
    *,
    name: str | None = None,
    code: StepCode = StepCode.ASSIGN_ROLES,
    phase: StepPhase = StepPhase.PREPARATION,
    actor: StepActor = StepActor.MANUAL,
    completed_at: datetime | None = None,
) -> str:
    return await _insert(
        Step(
            event_id=event_id,
            step_order=step_order,
            name=name or f"단계 {step_order}",
            code=code,
            phase=phase,
            actor=actor,
            completed_at=completed_at,
        )
    )


async def add_action(
    event_id: str,
    *,
    step_id: str | None = None,
    title: str = "공지 올리기",
    type: ActionType = ActionType.NOTICE,
    status: ActionStatus = ActionStatus.PENDING,
    approve_needed: bool = True,
    due_date: date | None = None,
    resolved_at: datetime | None = None,
    resolved_by: str | None = None,
    content: str | None = None,
    payload: dict | None = None,
) -> str:
    return await _insert(
        Action(
            event_id=event_id,
            step_id=step_id,
            title=title,
            type=type,
            status=status,
            approve_needed=approve_needed,
            due_date=due_date,
            resolved_at=resolved_at,
            resolved_by=resolved_by,
            content=content,
            payload=payload,
        )
    )
