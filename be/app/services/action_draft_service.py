"""운영 중 공지·발송 Action의 본문 초안 (#334).

단계가 현재 단계가 되면(행사 시작, 단계 완료) 그 단계의 공지·발송 Action을 "작성 중"으로
표시하고, 요청 응답과 별개로 뒤에서 AI 초안을 받아 Action.content에 저장한다.

    POST /steps/{id}/complete → 단계 완료, 커밋
      → request_current_step_drafts(event_id)
           현재 단계의 대상 Action → content_status=DRAFTING, draft_attempt_id=A1, 커밋
           spawn_draft(action_id, A1)   ← asyncio 작업. 응답은 기다리지 않는다
      → 응답 즉시 반환

    뒤에서 _run_draft(action_id, A1)   (새 세션)
      → Event·Step·Action·Club 읽기 → ActionDraftRequest (날짜는 한국 시간 날짜)
      → 잠금 없이 ai.draft_action_content(request)
      → 행사·Action 잠금 → 저장 조건 확인 → READY 저장(version +1) 또는 FAILED

계획 검토(plan_review_service.request_review)와 같은 순서다. AI를 부르기 전에 커밋하고,
모델을 기다리는 동안 DB 잠금을 쥐지 않는다. 판정(대상인지, 다시 받을 수 있는지, 멈춘
작성인지)은 event_rules의 순수 함수에 맡긴다.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import ai
from app.core.enums import ActionContentSource, ActionContentStatus, ActionStatus, StepState
from app.core.exceptions import ActionNotFound, ApiError, VersionConflict
from app.db.session import get_sessionmaker
from app.models.events import Action, Event, Step
from app.services import event_rules, event_service

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")

# 실행 중인 초안 작업의 참조. asyncio는 작업을 약한 참조로만 들고 있어, 참조가 없으면
# 작업이 중간에 정리될 수 있다(planning_stream._running과 같은 이유).
_running: set[asyncio.Task] = set()


class DraftNotAllowed(ApiError):
    """운영 중이 아니거나, PENDING이 아니거나, 대상 종류가 아니거나, 운영진이 고친 글이거나,
    작성 중이고 3분이 안 됐을 때. 이유는 응답의 canRequestDraft로 이미 알 수 있다."""

    status_code = 409
    code = "DRAFT_NOT_ALLOWED"

    def __init__(self) -> None:
        super().__init__("지금은 초안을 다시 받을 수 없어요. 목록을 다시 불러와 주세요.")


# --- 작업 띄우기 --------------------------------------------------------------


def _forget(task: asyncio.Task) -> None:
    _running.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        # _run_draft는 AI 오류를 FAILED로 남기므로 여기 오는 것은 저장 중 오류다.
        logger.error("본문 초안 작업 예외", exc_info=error)


def spawn_draft(action_id: str, attempt_id: str) -> None:
    """초안 작업을 뒤에서 띄운다. 테스트는 이 함수를 바꿔 끼워 작업을 직접 기다린다."""
    task = asyncio.create_task(_run_draft(action_id, attempt_id))
    _running.add(task)
    task.add_done_callback(_forget)


def _start(action_id: str, attempt_id: str) -> None:
    # 작업을 못 띄워도 호출한 쪽(행사 시작·단계 완료)은 성공해야 한다. DRAFTING으로 남은
    # Action은 3분 뒤 FAILED로 보이고 「다시 받기」로 복구한다.
    try:
        spawn_draft(action_id, attempt_id)
    except Exception:
        logger.exception("본문 초안 작업을 띄우지 못함: action=%s", action_id)


def _mark_drafting(action: Action, now: datetime) -> str:
    attempt_id = uuid4().hex
    action.content_status = ActionContentStatus.DRAFTING
    action.draft_attempt_id = attempt_id
    action.draft_started_at = now
    action.draft_error_code = None
    return attempt_id


# --- 신호: 현재 단계가 바뀔 수 있는 곳 -------------------------------------------


async def request_current_step_drafts(event_id: str) -> None:
    """현재 단계의 공지·발송 Action에 초안을 요청한다. 호출한 쪽이 커밋한 뒤에 부른다.

    action_service의 start_event·mark_done·resolve·complete_step이 부른다. 무슨 일이
    있어도 예외를 내지 않는다 — 호출한 쪽의 응답이 초안 때문에 실패하면 안 된다.
    요청 세션과 섞이지 않도록 새 세션을 쓴다.
    """
    try:
        started = await _mark_current_step(event_id)
    except Exception:
        logger.exception("본문 초안 요청 표시 실패: event=%s", event_id)
        return
    for action_id, attempt_id in started:
        _start(action_id, attempt_id)


async def _mark_current_step(event_id: str) -> list[tuple[str, str]]:
    async with get_sessionmaker()() as session:
        # 행사 → Action 순서로 잠근다(update_action, 승인 API와 같은 순서).
        event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None or not event_rules.is_operating(event.status):
            # 계획 중(P1·P2)에는 초안을 쓰지 않는다.
            return []
        steps = list(
            await session.scalars(
                select(Step).where(Step.event_id == event_id).order_by(Step.step_order)
            )
        )
        states = event_rules.step_states(steps, event_status=event.status)
        current = next((s for s in steps if states[s.id] == StepState.CURRENT), None)
        if current is None:
            return []
        # 미리 승인한 Action은 PENDING이 아니라 대상이 아니다. 승인한 내용을 바꾸지 않는다.
        actions = list(
            await session.scalars(
                select(Action)
                .where(
                    Action.step_id == current.id,
                    Action.type.in_(event_rules.DRAFT_ACTION_TYPES),
                    Action.status == ActionStatus.PENDING,
                    Action.content_status == ActionContentStatus.NONE,
                    func.coalesce(func.btrim(Action.content), "") == "",
                )
                .order_by(Action.created_at, Action.id)
                .with_for_update()
            )
        )
        now = datetime.now(UTC)
        started = [(action.id, _mark_drafting(action, now)) for action in actions]
        await session.commit()
        return started


# --- 「초안 다시 받기」 -----------------------------------------------------------


async def request_redraft(
    session: AsyncSession, *, action_id: str, expected_version: int
) -> tuple[Event, Action]:
    """POST /actions/{id}/draft. DRAFTING으로 바꾸고 새 시도로 작업을 띄운다.

    허용 조건은 응답의 canRequestDraft와 같은 event_rules.can_request_draft다. 운영 중이
    아닌 행사도 EVENT_NOT_ON_GOING이 아니라 DRAFT_NOT_ALLOWED로 알린다(#334 약속).
    """
    event = await session.scalar(
        select(Event)
        .join(Action, Action.event_id == Event.id)
        .where(Action.id == action_id)
        .with_for_update(of=Event)
        .execution_options(populate_existing=True)
    )
    action = await session.scalar(
        select(Action).where(Action.id == action_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if event is None or action is None:
        raise ActionNotFound()
    now = datetime.now(UTC)
    if not event_rules.can_request_draft(
        event_status=event.status,
        action_status=action.status,
        action_type=action.type,
        content_status=action.content_status,
        content_source=action.content_source,
        draft_started_at=action.draft_started_at,
        now=now,
    ):
        raise DraftNotAllowed()
    # 상태 검사 뒤에 본다(action_service._check_version과 같은 순서).
    if action.version != expected_version:
        raise VersionConflict()
    attempt_id = _mark_drafting(action, now)
    # 작성 중에는 이전 토리 초안을 보여 주지 않는다. 운영진이 고친 글(USER)은 여기 오지 않는다.
    action.content = None
    action.content_source = None
    action.content_unknowns = []
    action.version += 1
    await session.commit()
    _start(action.id, attempt_id)
    reloaded = await session.scalar(
        select(Action)
        .where(Action.id == action_id)
        .options(selectinload(Action.step), selectinload(Action.resolver))
        .execution_options(populate_existing=True)
    )
    return event, reloaded


# --- 뒤에서 도는 작업 -------------------------------------------------------------


def kst_date(value: datetime | None) -> date | None:
    """시각+시간대 값을 한국 시간 날짜로. 예: 2026-04-30T15:00:00Z → 2026-05-01."""
    return value.astimezone(_KST).date() if value is not None else None


def build_request(action: Action, *, today: date) -> "ai.ActionDraftRequest":
    """Action(step·event·club을 불러온)에서 AI 입력을 만든다. 총예산은 넣지 않는다."""
    event = action.event
    step = action.step
    return ai.ActionDraftRequest(
        club_name=event.club.name,
        event=ai.ActionDraftEvent(
            title=event.title,
            event_type=event.event_type,
            start_date=event.start_date,
            end_date=event.end_date,
            location=event.location,
            expected_headcount=event.expected_headcount,
            fee_per_person=event.fee_per_person,
        ),
        step=ai.ActionDraftStep(
            code=step.code,
            name=step.name,
            starts_on=kst_date(step.starts_at),
            deadline=kst_date(step.deadline),
        ),
        action=ai.ActionDraftAction(
            type=action.type,
            title=action.title,
            due_date=action.due_date,
            amount=action.amount,
        ),
        today=today,
    )


def _error_code(error: Exception) -> str:
    # AIInvalidResponseError는 AIRetryableError의 하위 타입이라 먼저 본다.
    if isinstance(error, ai.AIInvalidResponseError):
        return "AI_INVALID_RESPONSE"
    if isinstance(error, ai.AIRetryableError):
        return "AI_UNAVAILABLE"
    # 그 밖의 예외(구현 전 NotImplementedError, 입력 검증 실패 등)도 FAILED로 남긴다.
    # 작업이 조용히 사라지면 Action이 3분 동안 작성 중으로 보인다.
    logger.error("본문 초안 작성 실패", exc_info=error)
    return "INTERNAL_ERROR"


async def _run_draft(action_id: str, attempt_id: str) -> None:
    try:
        async with get_sessionmaker()() as session:
            action = await session.scalar(
                select(Action)
                .where(Action.id == action_id)
                .options(
                    selectinload(Action.step),
                    selectinload(Action.event).selectinload(Event.club),
                )
            )
            if action is None or action.step is None:
                return
            request = build_request(action, today=event_service.today_kst())
        # 세션을 닫은 뒤 모델을 부른다. 기다리는 동안 잠금·커넥션을 쥐지 않는다.
        result = await ai.draft_action_content(request)
    except Exception as error:
        await _finish(action_id, attempt_id, error_code=_error_code(error))
        return
    await _finish(action_id, attempt_id, result=result)


async def _finish(
    action_id: str,
    attempt_id: str,
    *,
    result: "ai.ActionDraftResult | None" = None,
    error_code: str | None = None,
) -> None:
    """저장 조건을 모두 만족할 때만 저장한다. 하나라도 어긋나면 결과를 버린다.

    - draft_attempt_id가 같음 (더 새 시도가 시작되지 않았음)
    - status == PENDING (그사이 승인·거절되지 않았음 → 승인한 내용과 본문이 달라지지 않게)
    - content가 비어 있거나 content_source == AI (운영진이 고친 글은 덮어쓰지 않음)
    - 행사가 아직 ON_GOING
    """
    async with get_sessionmaker()() as session:
        event = await session.scalar(
            select(Event)
            .join(Action, Action.event_id == Event.id)
            .where(Action.id == action_id)
            .with_for_update(of=Event)
        )
        action = await session.scalar(
            select(Action).where(Action.id == action_id).with_for_update()
        )
        if event is None or action is None or action.draft_attempt_id != attempt_id:
            return
        writable = (
            event_rules.is_operating(event.status)
            and action.status == ActionStatus.PENDING
            and (not (action.content or "").strip() or action.content_source == ActionContentSource.AI)
        )
        if not writable:
            # 결과는 버린다. 이 시도가 남긴 "작성 중" 표시만 걷어 낸다(승인된 카드가 3분 뒤
            # 실패로 보이지 않게). 운영진이 고친 글은 이미 READY라 건드리지 않는다.
            if action.content_status == ActionContentStatus.DRAFTING:
                action.content_status = ActionContentStatus.NONE
                await session.commit()
            return
        if result is not None:
            action.content = result.content
            action.content_source = ActionContentSource.AI
            action.content_unknowns = list(result.unknowns)
            action.content_status = ActionContentStatus.READY
            action.draft_error_code = None
            # 초안이 오기 전의 화면을 보고 승인하면 VERSION_CONFLICT가 난다. 운영진이 본 적
            # 없는 본문을 승인하는 일을 막는다.
            action.version += 1
        else:
            action.content_status = ActionContentStatus.FAILED
            action.draft_error_code = error_code
        await session.commit()
