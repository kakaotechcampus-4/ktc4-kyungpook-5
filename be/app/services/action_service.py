"""계획 확정, 행동 처리와 단계 완료 (#41).

계획을 확정하면(PLANNING → ON_GOING) 운영이 시작되고, 그때부터 승인·거절·확인 요청
응답·실행 완료·단계 완료를 받는다(#177 — 운영 시작 후의 일). 계획 중에는 다시 생성하면
행동이 새로 만들어지므로 처리를 받지 않는다.

승인·거절·확인 요청 응답·실행 완료는 task_service처럼 행을 잠그고 상태와 version을
확인한 뒤 바꾼다(낙관적 잠금). 상태 전이 판정은 event_rules의 순수 함수에 맡긴다.

행동이 DONE이 되면 그 단계의 행동이 모두 끝났는지 보고 단계 completed_at을 자동으로
채운다(FE 명세 v1 §819). 같은 단계의 두 행동이 동시에 끝나도 단계를 놓치지 않도록
단계 행도 잠그고 확인한다.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ActionStatus, EventStatus
from app.core.exceptions import (
    ApiError,
    EventNotFound,
    EventNotOnGoing,
    EventNotPlanning,
    PlanIncomplete,
    ValidationFailed,
    VersionConflict,
)
from app.models.clubs import Member
from app.models.events import Action, Event, Step
from app.services import event_rules

MANUAL_CHOICE = "MANUAL"


class ActionNotFound(ApiError):
    status_code = 404
    code = "ACTION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 행동을 찾을 수 없습니다.")


class StepNotFound(ApiError):
    status_code = 404
    code = "STEP_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 단계를 찾을 수 없습니다.")


class AlreadyResolved(ApiError):
    """다른 운영진이 먼저 처리했거나, 지금 상태에서 할 수 없는 처리일 때 (명세 v1)."""

    status_code = 409
    code = "ALREADY_RESOLVED"

    def __init__(self) -> None:
        super().__init__("이미 처리된 행동입니다. 목록을 다시 불러와 주세요.")


class StepAlreadyCompleted(ApiError):
    status_code = 409
    code = "STEP_ALREADY_COMPLETED"

    def __init__(self) -> None:
        super().__init__("이미 완료 처리된 단계입니다.")


async def action_event(session: AsyncSession, action_id: str) -> Event:
    """권한 확인용으로 행동이 속한 행사를 찾는다. 잠그지 않는다."""
    event = await session.scalar(
        select(Event).join(Action, Action.event_id == Event.id).where(Action.id == action_id)
    )
    if event is None:
        raise ActionNotFound()
    return event


async def step_event(session: AsyncSession, step_id: str) -> Event:
    event = await session.scalar(
        select(Event).join(Step, Step.event_id == Event.id).where(Step.id == step_id)
    )
    if event is None:
        raise StepNotFound()
    return event


def ensure_operating(event: Event) -> None:
    if not event_rules.is_operating(event.status):
        raise EventNotOnGoing()


async def start_event(session: AsyncSession, *, event_id: str) -> Event:
    """계획을 확정해 운영을 시작한다. 첫 단계부터 진행 상태가 계산된다(#213, FE 명세 v1 :confirm)."""
    event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
    if event is None:
        raise EventNotFound()
    if event.status != EventStatus.PLANNING:
        raise EventNotPlanning()
    missing: dict[str, str] = {}
    if event.start_date is None:
        missing["startDate"] = "행사 시작일이 필요합니다."
    step_count = await session.scalar(
        select(func.count()).select_from(Step).where(Step.event_id == event_id)
    )
    if not step_count:
        missing["steps"] = "계획 단계가 필요합니다. 흐름을 먼저 만들어 주세요."
    if missing:
        raise PlanIncomplete(missing)
    event.status = EventStatus.ON_GOING
    await session.commit()
    return event


async def _lock_action(session: AsyncSession, action_id: str) -> Action:
    action = await session.scalar(
        select(Action).where(Action.id == action_id).with_for_update()
    )
    if action is None:
        raise ActionNotFound()
    return action


def _check_version(action: Action, expected_version: int) -> None:
    """상태 검사 뒤에 본다. 이미 처리된 행동은 ALREADY_RESOLVED(명세 v1)로, 아직 대기
    중인데 본 뒤에 내용이 바뀐 행동은 VERSION_CONFLICT로 구분해 알려 준다."""
    if action.version != expected_version:
        # 본 적 없는 내용을 승인·처리하지 않도록 다시 불러오게 한다.
        raise VersionConflict()


def _not_confirmation(action: Action) -> None:
    if event_rules.is_confirmation(action.type):
        raise ValidationFailed({"type": "확인 요청은 /resolve로 처리합니다."})


async def _finish_step_if_done(session: AsyncSession, step_id: str | None) -> None:
    """단계의 행동이 모두 DONE이 되면 단계를 자동 완료한다. 처리자는 남기지 않는다."""
    if step_id is None:
        return
    step = await session.scalar(select(Step).where(Step.id == step_id).with_for_update())
    if step is None or step.completed_at is not None:
        return
    statuses = list(await session.scalars(select(Action.status).where(Action.step_id == step_id)))
    if event_rules.is_step_done(statuses):
        step.completed_at = datetime.now(UTC)


async def _reload(session: AsyncSession, action_id: str) -> Action:
    """응답(action_out)에 필요한 step·resolver를 함께 다시 읽는다."""
    return await session.scalar(
        select(Action)
        .where(Action.id == action_id)
        .options(selectinload(Action.step), selectinload(Action.resolver))
        .execution_options(populate_existing=True)
    )


def _set_resolution(action: Action, member: Member, status: ActionStatus) -> None:
    action.status = status
    action.resolved_at = datetime.now(UTC)
    action.resolved_by = member.id
    action.version += 1


async def approve(
    session: AsyncSession, *, action_id: str, member: Member, expected_version: int
) -> Action:
    action = await _lock_action(session, action_id)
    _not_confirmation(action)
    if not action.approve_needed:
        raise ValidationFailed({"actionId": "승인이 필요 없는 행동입니다."})
    if not event_rules.can_resolve(member.role, action.status):
        raise AlreadyResolved()
    _check_version(action, expected_version)
    _set_resolution(action, member, ActionStatus.APPROVED)
    await session.commit()
    return await _reload(session, action_id)


async def deny(
    session: AsyncSession,
    *,
    action_id: str,
    member: Member,
    expected_version: int,
    reason: str | None,
) -> Action:
    action = await _lock_action(session, action_id)
    _not_confirmation(action)
    if not event_rules.can_resolve(member.role, action.status):
        raise AlreadyResolved()
    _check_version(action, expected_version)
    _set_resolution(action, member, ActionStatus.DENIED)
    action.deny_reason = reason or None
    await session.commit()
    return await _reload(session, action_id)


async def resolve(
    session: AsyncSession,
    *,
    action_id: str,
    member: Member,
    expected_version: int,
    choice: str,
    manual_value: str | None,
) -> Action:
    action = await _lock_action(session, action_id)
    if not event_rules.is_confirmation(action.type):
        raise ValidationFailed({"type": "확인 요청만 /resolve로 처리합니다."})
    if not event_rules.can_resolve(member.role, action.status):
        raise AlreadyResolved()
    _check_version(action, expected_version)

    payload = dict(action.payload or {})
    option_keys = {option.get("key") for option in payload.get("options") or []}
    if choice == MANUAL_CHOICE:
        if not payload.get("allow_manual"):
            raise ValidationFailed({"choice": "직접 처리할 수 없는 확인 요청입니다."})
        if not manual_value:
            raise ValidationFailed({"manualValue": "직접 처리한 내용을 입력해 주세요."})
    elif choice not in option_keys:
        raise ValidationFailed({"choice": "선택지에 없는 값입니다."})

    # 고른 답은 선택지와 같은 payload(JSONB)에 둔다. 새 dict로 바꿔야 변경이 저장된다.
    payload["resolved_choice"] = choice
    payload["manual_value"] = manual_value if choice == MANUAL_CHOICE else None
    action.payload = payload
    _set_resolution(action, member, ActionStatus.DONE)
    await _finish_step_if_done(session, action.step_id)
    await session.commit()
    return await _reload(session, action_id)


async def mark_done(
    session: AsyncSession, *, action_id: str, member: Member, expected_version: int
) -> Action:
    """운영진이 직접 실행을 마쳤다는 기록. 처리자는 승인한 사람 그대로 둔다."""
    action = await _lock_action(session, action_id)
    _not_confirmation(action)
    if not event_rules.can_mark_done(action.status, approve_needed=action.approve_needed):
        raise AlreadyResolved()
    _check_version(action, expected_version)
    if action.resolved_by is None:
        # 승인이 필요 없는 행동은 실행을 기록한 사람이 처리자다.
        action.resolved_by = member.id
        action.resolved_at = datetime.now(UTC)
    action.status = ActionStatus.DONE
    action.version += 1
    await _finish_step_if_done(session, action.step_id)
    await session.commit()
    return await _reload(session, action_id)


async def complete_step(session: AsyncSession, *, step_id: str, member: Member) -> dict:
    """단계를 사람이 직접 완료 처리한다. 미처리 행동이 남아 있어도 완료할 수 있다(명세 v1)."""
    step = await session.scalar(select(Step).where(Step.id == step_id).with_for_update())
    if step is None:
        raise StepNotFound()
    if step.completed_at is not None:
        # 최초 완료 시점·처리자를 덮어쓰지 않는다.
        raise StepAlreadyCompleted()
    step.completed_at = datetime.now(UTC)
    step.completed_by = member.id
    pending = await session.scalar(
        select(func.count())
        .select_from(Action)
        .where(
            Action.step_id == step_id,
            Action.status.in_((ActionStatus.PENDING, ActionStatus.APPROVED)),
        )
    )
    await session.commit()
    return {
        "id": step.id,
        "completed_at": step.completed_at,
        "completed_by": {"id": member.id, "name": member.name, "role": member.role},
        "pending_action_count": pending or 0,
    }
