"""단계 완료 엔드포인트 (#41).

행동이 없는 MANUAL 단계나, 행동이 실패해 오프라인으로 처리한 단계를 사람이 직접
완료한다. 행동이 모두 끝난 단계는 서버가 자동으로 완료하므로 이 경로가 필요 없다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope
from app.schemas.events import StepCompleteOut
from app.services import action_service

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
