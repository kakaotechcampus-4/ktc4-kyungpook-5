"""행사 관련 엔드포인트.

조회(목록·상세·단계·행동, #41)와 P1·P2 계획 흐름(#187) 모두 실제 DB로 동작하며,
동아리 소속을 확인한 뒤에만 응답한다.
"""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.deps import ensure_member, get_current_account
from app.core.enums import ActionStatus, ActionType, EventStatus
from app.core.exceptions import ValidationFailed
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.events import Event, Step
from app.models.chat import Conversation, Message
from app.core.enums import MessageRole
from app.schemas.events import (
    ActionListResponse,
    DraftListResponse,
    DraftOut,
    EventCreateIn,
    EventCreateOut,
    EventDetailOut,
    EventListResponse,
    PlanChatIn,
    PlanMessageOut,
    PlanMessageListResponse,
    PlannedStepOut,
    PlannedStepListResponse,
    PlanGenerateIn,
    PlanScreenOut,
    PlanViewOut,
    StepListResponse,
)
from app.schemas.common import Envelope
from app.services import event_service, planning_service

router = APIRouter(prefix="/api/v1/events", tags=["events"])


async def _get_event_for_account(
    session: AsyncSession, *, event_id: str, account: Account
) -> tuple[Event, Member]:
    """club_id가 URL에 없는 라우트용. 행사를 찾은 뒤 그 동아리 소속인지 본다."""
    event = await session.get(Event, event_id)
    if event is None:
        raise planning_service.EventNotFound()
    member = await ensure_member(session, club_id=event.club_id, account=account)
    return event, member


@router.get("", response_model=EventListResponse)
async def list_events(
    # /records·/events/drafts처럼 어느 동아리 목록인지 명시한다. 한 계정이 여러
    # 동아리에 속할 수 있어 서버가 추측하지 않는다.
    club_id: str = Query(alias="clubId"),
    status: EventStatus | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> EventListResponse:
    await ensure_member(session, club_id=club_id, account=account)
    rows, total_count = await event_service.list_events(
        session, club_id=club_id, status=status, page=page, size=size
    )
    return EventListResponse.model_validate(
        {"data": rows, "meta": {"page": page, "size": size, "total_count": total_count}}
    )


# {event_id}/... 보다 먼저 등록한다. 뒤에 두면 "drafts"가 event_id로 해석된다.
@router.get("/drafts", response_model=DraftListResponse)
async def list_drafts(
    club_id: str = Query(alias="clubId"),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> DraftListResponse:
    await ensure_member(session, club_id=club_id, account=account)
    rows = await planning_service.list_drafts(session, club_id=club_id)
    return DraftListResponse(data=[DraftOut.model_validate(row) for row in rows])


@router.post("", response_model=Envelope[EventCreateOut], status_code=201)
async def create_event(
    body: EventCreateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[EventCreateOut]:
    await ensure_member(session, club_id=body.club_id, account=account)
    event = await planning_service.create_event(
        session, club_id=body.club_id, title=body.title
    )
    return Envelope(data=EventCreateOut.model_validate(event))


# /drafts보다 뒤에 둔다 — 앞에 두면 "drafts"가 event_id로 해석된다.
@router.get("/{event_id}", response_model=Envelope[EventDetailOut])
async def get_event(
    event_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[EventDetailOut]:
    event, _member = await _get_event_for_account(
        session, event_id=event_id, account=account
    )
    detail = await event_service.get_event_detail(session, event=event)
    return Envelope(data=EventDetailOut.model_validate(detail))


@router.post("/{event_id}/plan/chat", response_model=Envelope[PlanViewOut])
async def chat_plan(
    event_id: str,
    body: PlanChatIn,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlanViewOut]:
    event, member = await _get_event_for_account(
        session, event_id=event_id, account=account
    )
    # chat()은 AI 호출 전후로 세션을 직접 열고 닫는다 — 여기서 받은 session은
    # 권한 확인에만 쓰고 그대로 넘기지 않는다(db/session.py 참고). 권한 확인
    # 쿼리가 연 트랜잭션을 AI 호출 내내 쥐고 있지 않도록 여기서 바로 닫는다
    # (#192 리뷰 — pg_stat_activity에서 idle in transaction으로 확인됨).
    await session.close()
    view = await planning_service.chat(
        club_id=event.club_id, event_id=event_id, member_id=member.id,
        message_id=body.message_id, message_content=body.message,
        base_revision=body.base_revision, idempotency_key=idempotency_key,
    )
    return Envelope(data=PlanViewOut.model_validate(view))


@router.get("/{event_id}/plan/messages", response_model=PlanMessageListResponse)
async def list_plan_messages(
    event_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> PlanMessageListResponse:
    event, _member = await _get_event_for_account(session, event_id=event_id, account=account)
    conversation = await session.scalar(
        select(Conversation).where(Conversation.event_id == event.id)
        .order_by(Conversation.created_at.desc()).limit(1)
    )
    if conversation is None:
        return PlanMessageListResponse(data=[])
    rows = await session.scalars(
        select(Message).where(Message.conversation_id == conversation.id,
                              Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]))
        .order_by(Message.seq)
    )
    return PlanMessageListResponse(data=[PlanMessageOut.model_validate(row) for row in rows])


@router.get("/{event_id}/plan/steps", response_model=PlannedStepListResponse)
async def list_planned_steps(
    event_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> PlannedStepListResponse:
    event, _member = await _get_event_for_account(session, event_id=event_id, account=account)
    rows = await session.scalars(select(Step).where(Step.event_id == event.id).order_by(Step.step_order))
    return PlannedStepListResponse(data=[PlannedStepOut.model_validate(row) for row in rows])


@router.post("/{event_id}/plan/generate", response_model=Envelope[PlanViewOut])
async def generate_plan(
    event_id: str,
    body: PlanGenerateIn,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlanViewOut]:
    event, member = await _get_event_for_account(
        session, event_id=event_id, account=account
    )
    # 위 chat_plan과 같은 이유로 AI 호출 전에 요청 세션을 닫는다(#192 리뷰).
    await session.close()
    view = await planning_service.generate(
        club_id=event.club_id, event_id=event_id, member_id=member.id,
        base_revision=body.base_revision,
        use_current_conditions=body.use_current_conditions,
        idempotency_key=idempotency_key,
    )
    return Envelope(data=PlanViewOut.model_validate(view))


@router.get("/{event_id}/plan", response_model=Envelope[PlanScreenOut])
async def get_plan(
    event_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PlanScreenOut]:
    event, _member = await _get_event_for_account(
        session, event_id=event_id, account=account
    )
    screen = await planning_service.get_plan_screen(
        session, club_id=event.club_id, event_id=event_id
    )
    return Envelope(data=PlanScreenOut.model_validate(screen))


def _parse_statuses(raw: str | None) -> list[ActionStatus] | None:
    """status=PENDING 과 status=APPROVED,DONE,DENIED 를 모두 받는다.

    enum 목록을 쉼표로 받는 형태라 FastAPI가 직접 검증해주지 못해 여기서 본다.
    """
    if raw is None:
        return None
    codes = [code.strip() for code in raw.split(",") if code.strip()]
    try:
        return [ActionStatus(code) for code in codes]
    except ValueError:
        allowed = ", ".join(ActionStatus)
        raise ValidationFailed({"status": f"허용되는 값: {allowed}"}) from None


@router.get("/{event_id}/actions", response_model=ActionListResponse)
async def list_event_actions(
    event_id: str,
    status: str | None = Query(
        None, description="쉼표로 여러 개. 예: PENDING, APPROVED,DONE,DENIED"
    ),
    type: ActionType | None = Query(None, description="이 유형만 조회"),
    exclude_type: ActionType | None = Query(
        None, alias="excludeType", description="이 유형만 제외"
    ),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> ActionListResponse:
    statuses = _parse_statuses(status)
    _event, member = await _get_event_for_account(
        session, event_id=event_id, account=account
    )
    rows, total_count = await event_service.list_actions(
        session,
        event_id=event_id,
        member=member,
        statuses=statuses,
        action_type=type,
        exclude_type=exclude_type,
        page=page,
        size=size,
    )
    return ActionListResponse.model_validate(
        {"data": rows, "meta": {"page": page, "size": size, "total_count": total_count}}
    )


@router.get("/{event_id}/steps", response_model=StepListResponse)
async def list_event_steps(
    event_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> StepListResponse:
    await _get_event_for_account(session, event_id=event_id, account=account)
    rows = await event_service.list_steps(session, event_id=event_id)
    return StepListResponse.model_validate({"data": rows, "meta": None})
