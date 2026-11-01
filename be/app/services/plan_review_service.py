"""계획 편집 버전과 AI 검토 기준 스냅샷 (#177).

버전은 PLANNING 계획이 실제로 바뀐 뒤에만 올린다 — 바뀌었는지 판단은 호출하는 쪽 몫이다.

검토 요청은 planning_service의 chat/generate와 같이 AI를 부르기 전에 커밋해서,
모델을 기다리는 동안 DB 커넥션·잠금을 쥐지 않는다.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError
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
from app.core.exceptions import EventStateConflict, VersionConflict
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
    """시각은 UTC로, 날짜는 그대로 쓴다 — 저장 시점마다 오프셋이 달라도 같은 순간이 같은 문자열이 되게."""
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).isoformat()
    return value.isoformat()


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


def _field_value(field: str, action: dict) -> Any:
    # 문자열이 아니라 값으로 비교한다 — 표기만 다른 같은 날짜를 변경으로 보지 않는다.
    value = action.get(field)
    return _d(value) if field == "due_date" else value


def _action_changes(code: StepCode, before: list[dict], after: list[dict]) -> list[ai.ActionChange]:
    old = {action["title"]: action for action in before}
    changes = []
    for action in after:
        previous = old.get(action["title"])
        if previous is None:
            continue
        for field in ("amount", "due_date"):
            if _field_value(field, previous) != _field_value(field, action):
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
        if (_dt(old["starts_at"]), _dt(old["deadline"])) != (
            _dt(step["starts_at"]),
            _dt(step["deadline"]),
        ):
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


# 처리 중 서버가 죽어도 「검토 중」에 갇히지 않게, 이보다 오래된 REVIEWING은 실패로 보인다.
REVIEW_TIMEOUT = timedelta(seconds=90)


def _timed_out(row: PlanReview, now: datetime) -> bool:
    return row.requested_at is None or now - row.requested_at > REVIEW_TIMEOUT


def review_out(row: PlanReview | None, *, now: datetime) -> dict | None:
    """PlanReviewOut 모양. 오래된 REVIEWING은 응답에서만 FAILED로 바꾼다(DB는 그대로)."""
    if row is None:
        return None
    status, error_code = row.status, row.error_code
    if status == PlanReviewStatus.REVIEWING and _timed_out(row, now):
        status, error_code = PlanReviewStatus.FAILED, "REVIEW_TIMEOUT"
    return {
        "status": status,
        "generated_revision": row.generated_revision,
        "reviewed_revision": row.reviewed_revision,
        "outcome": row.outcome,
        "items": [
            {
                **item,
                # 이름은 AI 출력이 아니라 카탈로그로 붙인다.
                "step_names": [PLANNING_STEP_NAMES.get(code, code) for code in item["step_codes"]],
            }
            for item in row.items or []
        ],
        "error_code": error_code,
    }


def _error_code(error: Exception) -> str | None:
    """AI 실패를 저장할 코드로 바꾼다. AI 실패가 아니면(버그) None."""
    # AIInvalidResponseError는 AIRetryableError의 하위 타입이라 먼저 본다.
    if isinstance(error, (ai.AIInvalidResponseError, PydanticValidationError)):
        return "AI_INVALID_RESPONSE"
    if isinstance(error, ai.AIConfigError):
        return "AI_MISCONFIGURED"
    if isinstance(error, ai.AIRetryableError):
        return "AI_UNAVAILABLE"
    if isinstance(error, ai.AIError):
        return "AI_INVALID_RESPONSE"
    return None


async def _lock_review(session: AsyncSession, event_id: str) -> PlanReview | None:
    # 앞선 트랜잭션에서 읽은 행이 세션에 남아 있어도 지금 DB 값으로 다시 채운다.
    return await session.scalar(
        select(PlanReview)
        .where(PlanReview.event_id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _store_result(
    session: AsyncSession,
    *,
    event_id: str,
    request_id: str,
    result: ai.PlanEditReviewResult | None = None,
    error_code: str | None = None,
) -> dict:
    """요청이 아직 최신일 때만 결과를 쓴다. 그사이 새 요청·재생성이 있었으면 버린다."""
    # 재생성(_finish → reset_baseline)과 같은 순서로 행사 → 검토 행을 잠근다.
    # events는 잠그기만 한다 — 쓰면 modified_at이 올라 사용자 수정으로 읽힌다.
    await session.execute(select(Event.id).where(Event.id == event_id).with_for_update())
    row = await _lock_review(session, event_id)
    now = datetime.now(UTC)
    current = (
        row is not None
        and row.request_id == request_id
        and row.status == PlanReviewStatus.REVIEWING
    )
    if current:
        if result is not None:
            row.status = PlanReviewStatus.DONE
            row.outcome = result.outcome
            row.items = [item.model_dump(mode="json") for item in result.items]
        else:
            row.status = PlanReviewStatus.FAILED
            row.error_code = error_code
        row.finished_at = now
    out = review_out(row, now=now)
    await session.commit()
    return out


async def request_review(session: AsyncSession, *, event: Event, expected_revision: int) -> dict:
    """지금 계획을 AI로 검토한다. AI 실패도 FAILED로 저장해 200으로 돌려준다."""
    # planning_service·event_service가 이 모듈을 불러오므로 순환을 피해 여기서 불러온다.
    from app.services import event_service, planning_service

    event_id = event.id
    # ① 행사 → ② 검토 행 순서로 잠근다. plan_revision은 세션에 남은 값 대신 지금 값을 읽는다.
    locked = (
        await session.execute(
            select(Event.status, Event.plan_revision, Event.plan_excluded_steps)
            .where(Event.id == event_id)
            .with_for_update()
        )
    ).one()
    if locked.status != EventStatus.PLANNING:
        raise EventStateConflict("계획 중인 행사만 검토할 수 있어요.")
    if locked.plan_revision != expected_revision:
        raise VersionConflict()
    row = await _lock_review(session, event_id)
    if row is None:
        raise EventStateConflict("초안을 만든 뒤 검토할 수 있어요.")

    # 생성 직후 그대로인 계획은 검토할 게 없다 — 직접 호출돼도 AI를 부르지 않는다.
    if row.status == PlanReviewStatus.NOT_REQUESTED and expected_revision == row.generated_revision:
        out = review_out(row, now=datetime.now(UTC))
        await session.commit()
        return out

    # ③ 같은 버전을 이미 끝냈거나 아직 검토 중이면 AI를 다시 부르지 않는다.
    now = datetime.now(UTC)
    if row.reviewed_revision == expected_revision and (
        row.status == PlanReviewStatus.DONE
        or (row.status == PlanReviewStatus.REVIEWING and not _timed_out(row, now))
    ):
        out = review_out(row, now=now)
        await session.commit()
        return out

    # ④ 요청을 만들고 REVIEWING으로 커밋한다 — AI를 기다리는 동안 잠금·커넥션을 놓는다.
    request = build_review_request(
        draft=await planning_service.current_draft(session, event_id),
        today=event_service.today_kst(),
        current=await snapshot_plan(session, event_id),
        baseline=row.baseline,
        ai_excluded=locked.plan_excluded_steps or [],
    )
    request_id = uuid4().hex
    row.status = PlanReviewStatus.REVIEWING
    row.request_id = request_id
    row.reviewed_revision = expected_revision
    row.outcome = None
    row.items = None
    row.error_code = None
    row.requested_at = now
    row.finished_at = None
    await session.commit()

    # ⑤ 트랜잭션 없이 모델을 부른다. ⑥ 결과는 요청이 아직 최신일 때만 저장한다.
    try:
        result = await ai.review_plan_edit(request)
    except Exception as error:
        code = _error_code(error)
        # 버그여도 행이 REVIEWING에 머물지 않게 실패로 남기고 다시 던진다.
        out = await _store_result(
            session, event_id=event_id, request_id=request_id,
            error_code=code or "INTERNAL_ERROR",
        )
        if code is None:
            raise
        return out
    return await _store_result(session, event_id=event_id, request_id=request_id, result=result)
