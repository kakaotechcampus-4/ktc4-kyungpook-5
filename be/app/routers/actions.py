"""행동 처리 엔드포인트 (#41).

M1 승인 대기·L2 결정 검토 모달·확인 요청 카드·Step 모달이 부른다. 요청에는 조회
응답의 version을 expectedVersion으로 그대로 보내고, 응답은 조회와 같은 ActionOut이다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import WRITER_ROLES, ensure_member, get_current_account
from app.core.exceptions import ActionNotFound, Forbidden
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.events import Action, Event, Step
from app.schemas.common import Envelope
from app.schemas.events import (
    ActionDenyIn,
    ActionOut,
    ActionResolveIn,
    ActionUpdateIn,
    ActionVersionIn,
    PlannedStepOut,
)
from app.services import action_service, event_service

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


async def _operating_member(
    session: AsyncSession, *, action_id: str, account: Account
) -> tuple[Event, Member]:
    """행동의 행사에 속한 운영진인지, 행사가 운영 중인지 본다."""
    event = await action_service.action_event(session, action_id)
    member = await ensure_member(session, club_id=event.club_id, account=account)
    action_service.ensure_operating(event)
    return event, member


def _out(action, *, member: Member, event: Event) -> Envelope[ActionOut]:
    return Envelope(
        data=ActionOut.model_validate(
            event_service.action_out(action, member=member, event_status=event.status)
        )
    )


@router.post("/{action_id}/approve", response_model=Envelope[ActionOut])
async def approve_action(
    action_id: str,
    body: ActionVersionIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ActionOut]:
    event, member = await _operating_member(session, action_id=action_id, account=account)
    action = await action_service.approve(
        session, action_id=action_id, member=member, expected_version=body.expected_version
    )
    return _out(action, member=member, event=event)


@router.post("/{action_id}/deny", response_model=Envelope[ActionOut])
async def deny_action(
    action_id: str,
    body: ActionDenyIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ActionOut]:
    event, member = await _operating_member(session, action_id=action_id, account=account)
    action = await action_service.deny(
        session, action_id=action_id, member=member,
        expected_version=body.expected_version, reason=body.reason,
    )
    return _out(action, member=member, event=event)


@router.post("/{action_id}/resolve", response_model=Envelope[ActionOut])
async def resolve_action(
    action_id: str,
    body: ActionResolveIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ActionOut]:
    """확인 요청에 답한다. 승인·거절이 아니라 선택지 중 하나(또는 MANUAL)를 고른다."""
    event, member = await _operating_member(session, action_id=action_id, account=account)
    action = await action_service.resolve(
        session, action_id=action_id, member=member,
        expected_version=body.expected_version,
        choice=body.choice, manual_value=body.manual_value,
    )
    return _out(action, member=member, event=event)


@router.post("/{action_id}/done", response_model=Envelope[ActionOut])
async def mark_action_done(
    action_id: str,
    body: ActionVersionIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ActionOut]:
    """운영진이 직접 실행을 마쳤다는 기록. 앱은 발송·이체를 대신하지 않는다."""
    event, member = await _operating_member(session, action_id=action_id, account=account)
    action = await action_service.mark_done(
        session, action_id=action_id, member=member, expected_version=body.expected_version
    )
    return _out(action, member=member, event=event)


@router.patch("/{action_id}", response_model=Envelope[PlannedStepOut])
async def update_action(
    action_id: str,
    body: ActionUpdateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlannedStepOut]:
    """행동 세부를 고친다 (#106 ④).

    승인·처리(/approve 등)와 달리 계획 중에도 부른다. 그래서 운영 중을 요구하는
    _operating_member를 쓰지 않고 소속·권한만 본다.
    """
    action = await session.scalar(
        select(Action)
        .where(Action.id == action_id)
        .options(selectinload(Action.step).selectinload(Step.actions), selectinload(Action.event))
        .with_for_update()
    )
    if action is None:
        raise ActionNotFound()
    member = await ensure_member(session, club_id=action.event.club_id, account=account)
    if member.role not in WRITER_ROLES:
        raise Forbidden()

    sent = set(body.model_fields_set)
    values = {
        key: getattr(body, key)
        for key in ("title", "subtitle", "amount", "due_date")
        if key in sent
    }
    # 보낸 키만 덮는다. 모달이 그리지 않는 키를 지우지 않기 위해서다.
    payload_values = (
        body.payload.model_dump(exclude_unset=True) if body.payload is not None else None
    )
    updated = await event_service.update_action(
        session,
        action=action,
        values=values,
        payload_values=payload_values,
        expected_version=body.expected_version,
    )
    # 고친 행동이 속한 단계를 통째로 돌려준다 — 화면이 그 단위로 다시 그린다.
    if updated.step is None:
        raise ActionNotFound()
    await session.refresh(updated.step, ["actions"])
    return Envelope(
        data=PlannedStepOut.model_validate(event_service.planned_step_out(updated.step))
    )
