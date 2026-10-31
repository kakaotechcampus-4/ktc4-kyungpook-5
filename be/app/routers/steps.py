"""단계 완료 엔드포인트 (#41).

행동이 없는 MANUAL 단계나, 행동이 실패해 오프라인으로 처리한 단계를 사람이 직접
완료한다. 행동이 모두 끝난 단계는 서버가 자동으로 완료하므로 이 경로가 필요 없다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import WRITER_ROLES, ensure_member, get_current_account
from app.core.exceptions import Forbidden, StepNotFound
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope
from app.models.events import Step
from app.schemas.events import PlannedStepOut, StepCompleteOut, StepUpdateIn
from app.services import action_service, event_service

router = APIRouter(prefix="/api/v1/steps", tags=["steps"])


@router.post("/{step_id}/complete", response_model=Envelope[StepCompleteOut])
async def complete_step(
    step_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[StepCompleteOut]:
    event = await action_service.step_event(session, step_id)
    member = await ensure_member(session, club_id=event.club_id, account=account)
    action_service.ensure_operating(event)
    result = await action_service.complete_step(session, step_id=step_id, member=member)
    return Envelope(data=StepCompleteOut.model_validate(result))


@router.patch("/{step_id}", response_model=Envelope[PlannedStepOut])
async def update_step(
    step_id: str,
    body: StepUpdateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlannedStepOut]:
    """단계 일정을 고친다 (#106 ④). 계획 화면의 세부 수정 모달이 부른다."""
    step = await session.scalar(
        select(Step)
        .where(Step.id == step_id)
        .options(selectinload(Step.actions), selectinload(Step.event))
    )
    if step is None:
        raise StepNotFound()
    member = await ensure_member(session, club_id=step.event.club_id, account=account)
    if member.role not in WRITER_ROLES:
        raise Forbidden()
    updated = await event_service.update_step(
        session,
        step=step,
        starts_at=body.starts_at,
        deadline=body.deadline,
        fields=set(body.model_fields_set),
    )
    return Envelope(data=PlannedStepOut.model_validate(event_service.planned_step_out(updated)))
