"""계획 편집 버전과 AI 검토 기준 스냅샷 (#177).

버전은 PLANNING 계획이 실제로 바뀐 뒤에만 올린다 — 바뀌었는지 판단은 호출하는 쪽 몫이다.
"""

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.util import identity_key

from app.core.enums import EventStatus, PlanReviewStatus
from app.models.events import Action, Event, PlanReview, Step


async def bump_plan_revision(session: AsyncSession, event_id: str) -> int | None:
    """plan_revision을 1 올리고 새 값을 돌려준다. PLANNING이 아니면 None.

    읽고 쓰지 않고 한 번의 UPDATE로 올려서 동시 저장에도 증가분을 잃지 않는다.
    """
    revision = await session.scalar(
        update(Event)
        .where(Event.id == event_id, Event.status == EventStatus.PLANNING)
        .values(plan_revision=Event.plan_revision + 1)
        .returning(Event.plan_revision)
        .execution_options(synchronize_session=False)
    )
    # 세션에 이미 올라온 Event가 옛 값을 들고 있지 않게 한다.
    loaded = session.identity_map.get(identity_key(Event, event_id))
    if loaded is not None:
        session.expire(loaded, ["plan_revision"])
    return revision


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def snapshot_plan(session: AsyncSession, event_id: str) -> dict:
    """현재 계획 모양. 단계는 step_order, 행동은 생성 순서로 담는다."""
    steps = (
        await session.scalars(
            select(Step).where(Step.event_id == event_id).order_by(Step.step_order)
        )
    ).all()
    actions = (
        await session.scalars(
            select(Action)
            .where(Action.event_id == event_id, Action.step_id.is_not(None))
            .order_by(Action.created_at, Action.id)
        )
    ).all()
    by_step: dict[str, list[dict]] = {}
    for action in actions:
        by_step.setdefault(action.step_id, []).append(
            {
                "title": action.title,
                "amount": action.amount,
                "due_date": _iso(action.due_date),
            }
        )
    return {
        "steps": [
            {
                "code": step.code.value,
                "starts_at": _iso(step.starts_at),
                "deadline": _iso(step.deadline),
                "actions": by_step.get(step.id, []),
            }
            for step in steps
        ]
    }


async def reset_baseline(session: AsyncSession, event_id: str, revision: int) -> None:
    """초안 생성 직후 계획을 기준으로 저장하고 검토 상태를 처음으로 되돌린다.

    plan_reviews만 쓴다. events를 건드리면 modified_at이 올라 사용자 수정으로 읽힌다.
    """
    baseline = await snapshot_plan(session, event_id)
    fields = {
        "baseline": baseline,
        "generated_revision": revision,
        "status": PlanReviewStatus.NOT_REQUESTED,
        "request_id": None,
        "reviewed_revision": None,
        "outcome": None,
        "items": None,
        "error_code": None,
        "requested_at": None,
        "finished_at": None,
    }
    statement = pg_insert(PlanReview).values(event_id=event_id, **fields)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[PlanReview.event_id],
            set_={**fields, "modified_at": func.now()},
        )
    )
