"""단계·Action 세부 수정 (#106 ④).

club_id가 URL에 없다. 단계·Action의 id만으로 들어오므로 행사 → 동아리를 거슬러
올라가 소속과 권한을 확인한다. 수정은 회장·임원만 한다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import WRITER_ROLES, ensure_member, get_current_account
from app.core.exceptions import ActionNotFound, Forbidden, StepNotFound
from app.db.session import get_session
from app.models.auth import Account
from app.models.events import Action, Step
from app.schemas.common import Envelope
from app.schemas.events import ActionUpdateIn, PlannedStepOut, StepUpdateIn
from app.services import event_service

steps_router = APIRouter(prefix="/api/v1/steps", tags=["events"])
actions_router = APIRouter(prefix="/api/v1/actions", tags=["events"])


async def _writer_of(session: AsyncSession, *, club_id: str, account: Account) -> None:
    member = await ensure_member(session, club_id=club_id, account=account)
    if member.role not in WRITER_ROLES:
        raise Forbidden()


@steps_router.patch("/{step_id}", response_model=Envelope[PlannedStepOut])
async def update_step(
    step_id: str,
    body: StepUpdateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlannedStepOut]:
    step = await session.scalar(
        select(Step)
        .where(Step.id == step_id)
        .options(selectinload(Step.actions), selectinload(Step.event))
    )
    if step is None:
        raise StepNotFound()
    await _writer_of(session, club_id=step.event.club_id, account=account)
    updated = await event_service.update_step(
        session,
        step=step,
        starts_at=body.starts_at,
        deadline=body.deadline,
        fields=set(body.model_fields_set),
    )
    return Envelope(data=PlannedStepOut.model_validate(event_service.planned_step_out(updated)))


@actions_router.patch("/{action_id}", response_model=Envelope[PlannedStepOut])
async def update_action(
    action_id: str,
    body: ActionUpdateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlannedStepOut]:
    action = await session.scalar(
        select(Action)
        .where(Action.id == action_id)
        .options(
            selectinload(Action.step).selectinload(Step.actions),
            selectinload(Action.event),
        )
    )
    if action is None:
        raise ActionNotFound()
    await _writer_of(session, club_id=action.event.club_id, account=account)

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
        session, action=action, values=values, payload_values=payload_values
    )
    # 고친 Action이 속한 단계를 통째로 돌려준다 — 화면이 그 단위로 다시 그린다.
    if updated.step is None:
        raise ActionNotFound()
    await session.refresh(updated.step, ["actions"])
    return Envelope(
        data=PlannedStepOut.model_validate(event_service.planned_step_out(updated.step))
    )
