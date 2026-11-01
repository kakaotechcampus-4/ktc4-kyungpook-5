"""계획 편집 버전과 AI 검토 기준 스냅샷 (#177).

버전은 PLANNING 계획이 실제로 바뀐 뒤에만 올린다 — 바뀌었는지 판단은 호출하는 쪽 몫이다.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.util import identity_key

from app import ai
from app.ai.planning_catalog import (
    PLANNING_STEP_ACTORS,
    PLANNING_STEP_NAMES,
    PLANNING_STEP_PHASES,
)
from app.core.enums import ActionType, EventStatus, PlanReviewStatus, StepCode
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
                "type": action.type.value,
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


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _phase_sequences(codes: list[StepCode]) -> dict:
    sequences: dict = {}
    for code in codes:
        sequences.setdefault(PLANNING_STEP_PHASES[code], []).append(code)
    return sequences


def _moved_codes(current: list[StepCode], baseline: list[StepCode]) -> tuple[StepCode, ...]:
    common = set(current) & set(baseline)
    now = _phase_sequences([c for c in current if c in common])
    before = _phase_sequences([c for c in baseline if c in common])
    moved = {
        code
        for phase, sequence in now.items()
        if sequence != before.get(phase)
        for code in sequence
        if sequence.index(code) != before.get(phase, []).index(code)
    }
    return tuple(code for code in current if code in moved)


def _action_changes(code: StepCode, before: list[dict], after: list[dict]) -> list[ai.ActionChange]:
    old = {action["title"]: action for action in before}
    changes = []
    for action in after:
        previous = old.get(action["title"])
        if previous is None:
            continue
        for field in ("amount", "due_date"):
            if previous.get(field) != action.get(field):
                changes.append(
                    ai.ActionChange(
                        code=code,
                        action_title=action["title"],
                        field=field,
                        before=_text(previous.get(field)),
                        after=_text(action.get(field)),
                    )
                )
    return changes


def build_review_request(
    *,
    draft: ai.PlanningDraft,
    today: date,
    current: dict,
    baseline: dict,
    ai_excluded: list[dict],
) -> ai.PlanEditReviewRequest:
    """생성 직후 계획(baseline) 대비 현재 계획의 수정 내역으로 검토 요청을 만든다. DB 접근 없음."""
    now_steps = {StepCode(step["code"]): step for step in current["steps"]}
    old_steps = {StepCode(step["code"]): step for step in baseline["steps"]}
    ai_reasons = {StepCode(item["code"]): item.get("reason") for item in ai_excluded}

    included = tuple(
        ai.ReviewStep(
            code=code,
            name=PLANNING_STEP_NAMES[code],
            phase=PLANNING_STEP_PHASES[code],
            actor=PLANNING_STEP_ACTORS[code],
            starts_at=_dt(step["starts_at"]),
            deadline=_dt(step["deadline"]),
            actions=tuple(
                ai.ReviewAction(
                    type=ActionType(action["type"]),
                    title=action["title"],
                    amount=action.get("amount"),
                    due_date=_d(action.get("due_date")),
                )
                for action in step["actions"]
            ),
        )
        for code, step in now_steps.items()
    )
    excluded = tuple(
        ai.ReviewExcludedStep(
            code=code,
            name=PLANNING_STEP_NAMES[code],
            excluded_by="ai" if code in ai_reasons else "user",
            reason=ai_reasons.get(code),
        )
        for code in PLANNING_STEP_NAMES
        if code not in now_steps
    )

    schedule_changes = []
    action_changes: list[ai.ActionChange] = []
    for code, step in now_steps.items():
        old = old_steps.get(code)
        if old is None:
            continue
        if (old["starts_at"], old["deadline"]) != (step["starts_at"], step["deadline"]):
            schedule_changes.append(
                ai.ScheduleChange(
                    code=code,
                    before_starts_at=_dt(old["starts_at"]),
                    before_deadline=_dt(old["deadline"]),
                    after_starts_at=_dt(step["starts_at"]),
                    after_deadline=_dt(step["deadline"]),
                )
            )
        action_changes.extend(_action_changes(code, old["actions"], step["actions"]))

    changes = ai.PlanChangeSet(
        removed_codes=tuple(c for c in old_steps if c not in now_steps),
        added_codes=tuple(c for c in now_steps if c not in old_steps),
        moved_codes=_moved_codes(list(now_steps), list(old_steps)),
        schedule_changes=tuple(schedule_changes),
        action_changes=tuple(action_changes),
    )
    return ai.PlanEditReviewRequest(
        draft=draft,
        today=today,
        included_steps=included,
        excluded_steps=excluded,
        changes=changes,
    )
