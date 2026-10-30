"""행사 조회 (#41).

행사·단계·행동을 DB에서 읽어 L1·L2·M1·P2 화면이 쓰는 응답 모양(dict)으로 만든다.
진행 상태·D-day·처리 권한 같은 판정은 event_rules의 순수 함수에 맡기고 여기서는
조합만 한다. 권한 확인(동아리 소속)은 라우터가 먼저 끝낸 뒤 부른다.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ActionStatus, ActionType, EventStatus, StepState
from app.models.clubs import Member
from app.models.events import Action, Event, Step
from app.services import event_rules

_KST = ZoneInfo("Asia/Seoul")

# M1 「승인 대기」와 같은 기준. 확인 요청은 L2에서 따로 보여서 세지 않는다.
_PENDING_APPROVAL = (
    Action.status == ActionStatus.PENDING,
    Action.type != ActionType.CONFIRMATION,
)

# 처리 안 된 것(resolved_at 없음)을 먼저 마감 임박 순으로, 처리된 것은 최근 처리 순으로
# 둔다. M1 승인 대기와 L2 「처리된 승인」 최근 3건이 같은 정렬 하나로 맞는다.
_ACTION_ORDER = (
    Action.resolved_at.desc().nulls_first(),
    Action.due_date.asc().nulls_last(),
    Action.created_at,
    Action.id,
)


def today_kst() -> date:
    """D-day 기준일. 서버 시간대가 UTC라 date.today()는 KST 0~9시에 하루 전이 된다."""
    return datetime.now(_KST).date()


def _current_step(
    steps: Sequence[Step], states: dict[str, StepState]
) -> Step | None:
    return next((s for s in steps if states[s.id] == StepState.CURRENT), None)


def _event_base(event: Event, today: date) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "status": event.status,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "dday": event_rules.dday(event.start_date, today),
        "location": event.location,
        # FE 명세 v1이 인원 필드명을 headcount로 통일해 컬럼명과 다르다.
        "headcount": event.expected_headcount,
        # accounting 기준으로 재정의하기 전까지 비워 둔다 (FE 연동 기준서 §5.1).
        "payment": None,
        "budget": None,
    }


async def _pending_approval_counts(
    session: AsyncSession, event_ids: list[str]
) -> dict[str, int]:
    if not event_ids:
        return {}
    rows = await session.execute(
        select(Action.event_id, func.count())
        .where(Action.event_id.in_(event_ids), *_PENDING_APPROVAL)
        .group_by(Action.event_id)
    )
    return dict(rows.tuples().all())


async def list_events(
    session: AsyncSession,
    *,
    club_id: str,
    status: EventStatus | None,
    page: int,
    size: int,
) -> tuple[list[dict], int]:
    """동아리의 행사 목록과 전체 건수. 시작일이 가까운 순이고 날짜 없는 행사는 뒤로 간다."""
    conditions = [Event.club_id == club_id]
    if status is not None:
        conditions.append(Event.status == status)

    total = await session.scalar(
        select(func.count()).select_from(Event).where(*conditions)
    )
    events = list(
        await session.scalars(
            select(Event)
            .where(*conditions)
            # 카드마다 단계를 따로 조회하지 않도록 한 번에 불러온다 (step_order 순).
            .options(selectinload(Event.steps))
            .order_by(
                Event.start_date.asc().nulls_last(), Event.created_at.desc(), Event.id
            )
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    pending_counts = await _pending_approval_counts(session, [e.id for e in events])

    today = today_kst()
    result = []
    for event in events:
        states = event_rules.step_states(event.steps)
        current = _current_step(event.steps, states)
        result.append(
            {
                **_event_base(event, today),
                "current_step_name": current.name if current else None,
                "step_progress": [
                    {"step_order": s.step_order, "state": states[s.id]}
                    for s in event.steps
                ],
                "pending_approval_count": pending_counts.get(event.id, 0),
            }
        )
    return result, total or 0


async def _ordered_steps(session: AsyncSession, event_id: str) -> list[Step]:
    return list(
        await session.scalars(
            select(Step).where(Step.event_id == event_id).order_by(Step.step_order)
        )
    )


async def get_event_detail(session: AsyncSession, *, event: Event) -> dict:
    """L2 헤더. event는 라우터가 권한 확인하며 이미 읽어 둔 행이다."""
    steps = await _ordered_steps(session, event.id)
    current = _current_step(steps, event_rules.step_states(steps))
    return {
        **_event_base(event, today_kst()),
        "current_step": (
            {"id": current.id, "step_order": current.step_order, "name": current.name}
            if current
            else None
        ),
    }


async def list_steps(session: AsyncSession, *, event_id: str) -> list[dict]:
    """행사의 단계를 step_order 순으로, 단계마다 한 일·남은 일을 붙여 돌려준다."""
    steps = await _ordered_steps(session, event_id)
    actions = await session.scalars(
        select(Action)
        .where(Action.event_id == event_id, Action.step_id.is_not(None))
        .order_by(*_ACTION_ORDER)
    )
    actions_by_step: dict[str, list[Action]] = defaultdict(list)
    for action in actions:
        actions_by_step[action.step_id].append(action)

    states = event_rules.step_states(steps)
    result = []
    for step in steps:
        step_actions = actions_by_step[step.id]
        done = [a for a in step_actions if a.status == ActionStatus.DONE]
        # 거절·실패는 한 일도 남은 일도 아니라 두 목록 어디에도 넣지 않는다.
        remaining = [
            a
            for a in step_actions
            if a.status in (ActionStatus.PENDING, ActionStatus.APPROVED)
        ]
        result.append(
            {
                "id": step.id,
                "step_order": step.step_order,
                "code": step.code,
                "phase": step.phase,
                "name": step.name,
                "actor": step.actor,
                "state": states[step.id],
                "starts_at": step.starts_at,
                "deadline": step.deadline,
                "completed_at": step.completed_at,
                "completed_count": len(done),
                "total_action_count": len(step_actions),
                "done_actions": [
                    {"id": a.id, "title": a.title, "status": a.status} for a in done
                ],
                "remaining_actions": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "status": a.status,
                        "approve_needed": a.approve_needed,
                    }
                    for a in remaining
                ],
            }
        )
    return result


def action_out(action: Action, *, member: Member, event_status: EventStatus) -> dict:
    """ActionOut 한 건. step·resolver를 미리 불러온 Action이어야 한다.

    member는 요청한 동아리원이다 — canApprove가 요청자 기준이라 필요하다. 처리는 운영 중
    행사에서만 받으므로 행사 상태도 함께 본다.
    승인·거절 API도 처리 결과를 이 함수로 내려 조회와 모양을 맞춘다.
    """
    payload = action.payload if action.type == ActionType.CONFIRMATION else None
    payload = payload or {}
    resolver = action.resolver
    return {
        "id": action.id,
        "type": action.type,
        "title": action.title,
        "subtitle": action.subtitle,
        "content": action.content,
        "irreversible": action.irreversible,
        "approve_needed": action.approve_needed,
        "status": action.status,
        "amount": action.amount,
        "due_date": action.due_date,
        "step_id": action.step_id,
        "step_name": action.step.name if action.step else None,
        "resolved_at": action.resolved_at,
        "resolved_by": (
            {"id": resolver.id, "name": resolver.name, "role": resolver.role}
            if resolver
            else None
        ),
        "deny_reason": action.deny_reason,
        # CONFIRMATION 선택지는 payload(JSONB)에 들어 있다. 응답 평탄화는 여기서만 한다.
        "options": payload.get("options"),
        "allow_manual": payload.get("allow_manual"),
        "can_approve": event_rules.can_approve(
            member.role,
            action.status,
            action_type=action.type,
            approve_needed=action.approve_needed,
            event_status=event_status,
        ),
        "editable": event_rules.is_editable(action.status),
        "resolved_choice": payload.get("resolved_choice"),
        "manual_value": payload.get("manual_value"),
        "version": action.version,
    }


async def list_actions(
    session: AsyncSession,
    *,
    event_id: str,
    member: Member,
    event_status: EventStatus,
    statuses: list[ActionStatus] | None,
    action_type: ActionType | None,
    exclude_type: ActionType | None,
    page: int,
    size: int,
) -> tuple[list[dict], int]:
    """행사의 Action 목록과 전체 건수.

    type과 exclude_type은 함께 쓰이지 않는다. 확인 요청만 보는 화면과 확인 요청만
    빼고 보는 화면이 둘 다 있어 파라미터가 두 개다.
    """
    conditions = [Action.event_id == event_id]
    if statuses:
        conditions.append(Action.status.in_(statuses))
    if action_type is not None:
        conditions.append(Action.type == action_type)
    if exclude_type is not None:
        conditions.append(Action.type != exclude_type)

    total = await session.scalar(
        select(func.count()).select_from(Action).where(*conditions)
    )
    actions = await session.scalars(
        select(Action)
        .where(*conditions)
        .options(selectinload(Action.step), selectinload(Action.resolver))
        .order_by(*_ACTION_ORDER)
        .offset((page - 1) * size)
        .limit(size)
    )
    return [
        action_out(a, member=member, event_status=event_status) for a in actions
    ], total or 0
