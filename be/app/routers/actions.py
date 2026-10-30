"""행동 처리 엔드포인트 (#41).

M1 승인 대기·L2 결정 검토 모달·확인 요청 카드·Step 모달이 부른다. 요청에는 조회
응답의 version을 expectedVersion으로 그대로 보내고, 응답은 조회와 같은 ActionOut이다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.events import Event
from app.schemas.common import Envelope
from app.schemas.events import ActionDenyIn, ActionOut, ActionResolveIn, ActionVersionIn
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
