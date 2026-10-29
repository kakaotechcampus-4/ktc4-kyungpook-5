"""P1 큰 틀 잡기 · P2 흐름 만들기를 app.ai에 연결한다 (#187).

AI 호출 중에는 트랜잭션을 잡지 않는다(db/session.py, #52) — 채팅 생성은 20초 넘게
걸릴 수 있어(p1-handoff.md), 그동안 커넥션을 쥐고 있으면 풀이 고갈된다. 그래서
chat()/generate()는 세션을 세 번 나눠 쓴다: (1) 짧은 세션으로 상태 조회·멱등성
PROCESSING 기록, (2) 세션 없이 app.ai 호출, (3) 새 짧은 세션으로 저장 — base_revision은
저장 직전에 다시 확인한다(그 사이 다른 요청이 먼저 저장했을 수 있어서).

검색 포트(records=)는 #141에서 실제 구현 전까지 주입하지 않는다 — Tool 없이 동작한다.
"""

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.ai as ai
from app.core import idempotency
from app.core.exceptions import (
    AIMisconfigured,
    AIUnavailable,
    ApiError,
    EventNotFound,
    PlanningStateConflict,
    VersionConflict,
)
from app.core.enums import ActionStatus, EventStatus, MessageRole, StepActor
from app.db.base import new_id
from app.db.session import get_sessionmaker
from app.models.chat import Conversation, Message
from app.models.common import IdempotencyKey
from app.models.events import Action, Event, Step

from app.services import event_rules

_KST = ZoneInfo("Asia/Seoul")


def _default_title(created_at: datetime) -> str:
    local = created_at.astimezone(_KST)
    return f"새 행사 · {local.month}월 {local.day}일"


async def get_event(session: AsyncSession, *, club_id: str, event_id: str) -> Event:
    event = await session.get(Event, event_id)
    if event is None or event.club_id != club_id:
        raise EventNotFound()
    return event


async def create_event(
    session: AsyncSession, *, club_id: str, title: str | None
) -> Event:
    """title을 비워두면 바로 기본값을 채운다 (#179) — 대화 중 정하면 그때 덮어쓴다."""
    event = Event(club_id=club_id, title=title or "", status=EventStatus.PLANNING)
    if not title:
        event.title = _default_title(datetime.now(UTC))
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_drafts(session: AsyncSession, *, club_id: str) -> list[Event]:
    rows = await session.scalars(
        select(Event)
        .where(Event.club_id == club_id, Event.status == EventStatus.PLANNING)
        .order_by(Event.created_at.desc())
    )
    return list(rows)


async def _get_or_create_conversation(
    session: AsyncSession, *, event_id: str, member_id: str
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.event_id == event_id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if conversation is not None:
        return conversation
    conversation = Conversation(member_id=member_id, event_id=event_id)
    session.add(conversation)
    await session.flush()
    return conversation


def _resume_state(conversation: Conversation) -> "ai.PlanningResumeState | None":
    if conversation.resume_state is None:
        return None
    return ai.parse_resume_state(json.dumps(conversation.resume_state))


def _draft_out(draft: "ai.PlanningDraft") -> dict:
    c = draft.conditions
    return {
        "conditions": {
            "title": c.title,
            "event_type": c.event_type,
            "headcount": c.headcount,
            "fee_per_person": c.fee_per_person,
            # date는 멱등성 응답 캐시(JSONB)에 그대로 못 들어가 ISO 문자열로 바꾼다.
            # PlanConditionsOut이 다시 date로 파싱한다.
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "location": c.location,
            "budget_total": c.budget_total,
        },
        "condition_meta": {
            field: {
                "status": meta.status,
                "evidence_message_id": meta.evidence.message_id,
                "evidence_quote": meta.evidence.quote,
            }
            for field, meta in draft.condition_meta.items()
        },
        "deferred_topics": list(draft.deferred_topics),
    }


def _view_out(result: "ai.PlanningPublicResult", *, base_revision: int) -> dict:
    view = result.view
    record_lookup = (
        {
            "status": view.record_lookup.status,
            "query": view.record_lookup.query,
            "reason": view.record_lookup.reason,
        }
        if view.record_lookup is not None
        else None
    )
    generation_result = (
        {"status": view.generation_result.status, "reason": view.generation_result.reason}
        if view.generation_result is not None
        else None
    )
    return {
        "reply": view.reply,
        "draft": _draft_out(view.draft),
        "changed_fields": list(view.changed_fields),
        "record_lookup": record_lookup,
        "generation_readiness": {
            "can_generate": view.generation_readiness.can_generate,
            "reasons": list(view.generation_readiness.reasons),
        },
        "generation_result": generation_result,
        "base_revision": base_revision,
    }


def _unwrap_planning_state_error(
    error: PydanticValidationError,
) -> "ai.PlanningStateError | None":
    """validate_resume() 등 model_validator 안에서 던진 PlanningStateError는 pydantic이
    ValidationError로 감싼다(p1-handoff.md §8). ctx.error로 원래 예외를 꺼낸다."""
    for detail in error.errors():
        cause = detail.get("ctx", {}).get("error")
        if isinstance(cause, ai.PlanningStateError):
            return cause
    return None


def _translate_ai_error(error: Exception) -> ApiError:
    if isinstance(error, PydanticValidationError):
        state_error = _unwrap_planning_state_error(error)
        if state_error is not None:
            return PlanningStateConflict()
        raise error
    if isinstance(error, ai.PlanningStateError):
        return PlanningStateConflict()
    if isinstance(error, ai.AIConfigError):
        return AIMisconfigured()
    if isinstance(error, ai.AIRetryableError):
        return AIUnavailable()
    raise error


async def _materialize_preview(
    session: AsyncSession, event: Event, preview: "ai.EventPlanPreview"
) -> None:
    """임시 미리보기를 실제 Step/Action으로 바꾼다. 항상 전체 교체 — 부분 patch는 #41."""
    await session.execute(delete(Action).where(Action.event_id == event.id))
    await session.execute(delete(Step).where(Step.event_id == event.id))
    await session.flush()

    for order, step in enumerate(preview.steps, start=1):
        step_row = Step(
            event_id=event.id,
            step_order=order,
            phase=step.phase,
            code=step.code,
            name=step.name,
            actor=step.actor,
            starts_at=step.starts_at,
            deadline=step.deadline,
        )
        session.add(step_row)
        await session.flush()
        for action in step.actions:
            irreversible, approve_needed = event_rules.action_defaults(action.type)
            session.add(
                Action(
                    event_id=event.id,
                    step_id=step_row.id,
                    type=action.type,
                    title=action.title,
                    due_date=action.due_date,
                    irreversible=irreversible,
                    approve_needed=approve_needed,
                    status=ActionStatus.PENDING,
                )
            )

    event.plan_warnings = [{"message": w} for w in preview.warnings]
    event.plan_excluded_steps = [
        {"code": excl.code.value, "reason": excl.reason}
        for excl in preview.excluded_steps
    ]
    event.saved_at = datetime.now(UTC)


async def _save_turn(
    session: AsyncSession,
    *,
    event: Event,
    conversation: Conversation,
    result: "ai.PlanningPublicResult",
    new_base_revision: int,
    user_message_text: str | None,
) -> None:
    conditions = result.view.draft.conditions
    event.title = conditions.title or event.title
    event.event_type = conditions.event_type
    event.location = conditions.location
    event.start_date = conditions.start_date
    event.end_date = conditions.end_date
    event.expected_headcount = conditions.headcount
    event.budget_total = conditions.budget_total
    event.fee_per_person = conditions.fee_per_person

    conversation.resume_state = result.next_state.model_dump(mode="json")
    # AI는 base_revision을 올리지 않고 받은 값을 그대로 돌려준다(p1-handoff.md §4).
    # 버전 증가는 BE 책임이다.
    conversation.base_revision = new_base_revision
    conversation.generation_readiness = result.view.generation_readiness.model_dump(
        mode="json"
    )

    next_seq = await session.scalar(
        select(func.max(Message.seq)).where(Message.conversation_id == conversation.id)
    )
    seq = (next_seq or 0) + 1
    if user_message_text is not None:
        session.add(
            Message(
                conversation_id=conversation.id,
                seq=seq,
                role=MessageRole.USER,
                content=user_message_text,
            )
        )
        seq += 1
    if result.view.reply:
        session.add(
            Message(
                conversation_id=conversation.id,
                seq=seq,
                role=MessageRole.ASSISTANT,
                content=result.view.reply,
            )
        )

    generation_result = result.view.generation_result
    if generation_result is not None and generation_result.status == "generated":
        await _materialize_preview(session, event, generation_result.preview)


async def _resolve_idempotency(
    session: AsyncSession,
    *,
    key: str | None,
    club_id: str,
    member_id: str,
    endpoint: str,
    request_body: bytes,
) -> idempotency.IdempotencyResult | None:
    result = await idempotency.resolve(
        session, key=key, club_id=club_id, member_id=member_id,
        endpoint=endpoint, request_body=request_body,
    )
    await session.commit()
    return result


async def _save_idempotency_response(record_id: str, *, status_code: int, body: dict) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await session.get(IdempotencyKey, record_id)
        if record is not None:
            await idempotency.save_response(
                session, record, status_code=status_code, body=body
            )
            await session.commit()


async def _release_idempotency(record_id: str) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await idempotency.release(session, record_id)
        await session.commit()


async def _run_once(idem: idempotency.IdempotencyResult | None, work) -> dict:
    """멱등키가 있으면 처리 결과를 저장하고, 실패하면 키를 풀어 같은 키로 다시
    시도할 수 있게 한다. 풀지 않으면 재시도가 처리 중(409)으로 막힌다."""
    if idem is not None and idem.is_replay:
        return idem.record.response_body
    try:
        out = await work()
    except Exception:
        if idem is not None:
            await _release_idempotency(idem.record.id)
        raise
    if idem is not None:
        await _save_idempotency_response(idem.record.id, status_code=200, body=out)
    return out


class _PreparedTurn:
    __slots__ = ("request", "club_id", "event_id", "member_id", "base_revision")

    def __init__(self, request, *, club_id, event_id, member_id, base_revision):
        self.request = request
        self.club_id = club_id
        self.event_id = event_id
        self.member_id = member_id
        self.base_revision = base_revision


async def _prepare(
    *,
    club_id: str,
    event_id: str,
    member_id: str,
    base_revision: int,
    build_request,
) -> tuple[_PreparedTurn, Event]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        event = await get_event(session, club_id=club_id, event_id=event_id)
        conversation = await _get_or_create_conversation(
            session, event_id=event.id, member_id=member_id
        )
        if conversation.base_revision != base_revision:
            raise VersionConflict()

        resume_state = _resume_state(conversation)
        draft = (
            resume_state.payload.basis_draft
            if resume_state is not None
            else ai.PlanningDraft()
        )
        context = {
            "request_id": new_id("req"),
            "club_id": club_id,
            "event_id": event.id,
            "conversation_id": conversation.id,
            "base_revision": base_revision,
            "draft": draft,
            "resume_state": resume_state,
            "reference_date": date.today(),
            "timezone": "Asia/Seoul",
        }
        request = build_request(context)
        await session.commit()
    return (
        _PreparedTurn(
            request, club_id=club_id, event_id=event_id,
            member_id=member_id, base_revision=base_revision,
        ),
        event,
    )


async def _finish(
    prepared: _PreparedTurn, result: "ai.PlanningPublicResult", *, user_message_text: str | None
) -> dict:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        event = await get_event(
            session, club_id=prepared.club_id, event_id=prepared.event_id
        )
        conversation = await _get_or_create_conversation(
            session, event_id=event.id, member_id=prepared.member_id
        )
        if conversation.base_revision != prepared.base_revision:
            # AI를 기다리는 동안 다른 요청이 먼저 저장했다. 이번 결과는 버린다.
            raise VersionConflict()

        new_base_revision = prepared.base_revision + 1
        await _save_turn(
            session, event=event, conversation=conversation, result=result,
            new_base_revision=new_base_revision, user_message_text=user_message_text,
        )
        out = _view_out(result, base_revision=new_base_revision)
        await session.commit()
    return out


async def chat(
    *,
    club_id: str,
    event_id: str,
    member_id: str,
    message_id: str,
    message_content: str,
    base_revision: int,
    idempotency_key: str | None,
) -> dict:
    sessionmaker = get_sessionmaker()
    endpoint = "POST /events/{event_id}/plan/chat"
    request_body = json.dumps(
        {"messageId": message_id, "message": message_content, "baseRevision": base_revision},
        sort_keys=True,
    ).encode()

    async with sessionmaker() as session:
        idem = await _resolve_idempotency(
            session, key=idempotency_key, club_id=club_id, member_id=member_id,
            endpoint=endpoint, request_body=request_body,
        )

    async def work() -> dict:
        prepared, _event = await _prepare(
            club_id=club_id, event_id=event_id, member_id=member_id,
            base_revision=base_revision,
            build_request=lambda ctx: ai.PlanningChatRequest(
                **ctx, message=ai.PlanningUserMessage(id=message_id, content=message_content)
            ),
        )
        try:
            result = await ai.chat_planning(prepared.request)
        except (ai.PlanningStateError, ai.AIError, PydanticValidationError) as error:
            raise _translate_ai_error(error) from error
        return await _finish(prepared, result, user_message_text=message_content)

    return await _run_once(idem, work)


async def generate(
    *,
    club_id: str,
    event_id: str,
    member_id: str,
    base_revision: int,
    use_current_conditions: bool,
    idempotency_key: str | None,
) -> dict:
    sessionmaker = get_sessionmaker()
    endpoint = "POST /events/{event_id}/plan/generate"
    request_body = json.dumps(
        {"baseRevision": base_revision, "useCurrentConditions": use_current_conditions},
        sort_keys=True,
    ).encode()

    async with sessionmaker() as session:
        idem = await _resolve_idempotency(
            session, key=idempotency_key, club_id=club_id, member_id=member_id,
            endpoint=endpoint, request_body=request_body,
        )

    async def work() -> dict:
        prepared, _event = await _prepare(
            club_id=club_id, event_id=event_id, member_id=member_id,
            base_revision=base_revision,
            build_request=lambda ctx: ai.PlanningPreviewRequest(
                **ctx, use_current_conditions=use_current_conditions
            ),
        )
        try:
            result = await ai.generate_planning_preview(prepared.request)
        except (ai.PlanningStateError, ai.AIError, PydanticValidationError) as error:
            raise _translate_ai_error(error) from error
        return await _finish(prepared, result, user_message_text=None)

    return await _run_once(idem, work)


async def get_plan_screen(
    session: AsyncSession, *, club_id: str, event_id: str
) -> dict:
    event = await get_event(session, club_id=club_id, event_id=event_id)
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.event_id == event.id)
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    resume_state = _resume_state(conversation) if conversation is not None else None
    draft = (
        resume_state.payload.basis_draft if resume_state is not None else ai.PlanningDraft()
    )

    total = await session.scalar(
        select(func.count()).select_from(Step).where(Step.event_id == event.id)
    )
    actor_counts = dict(
        (
            await session.execute(
                select(Step.actor, func.count())
                .where(Step.event_id == event.id)
                .group_by(Step.actor)
            )
        ).all()
    )
    return {
        "draft": _draft_out(draft),
        "warnings": [w.get("message", "") for w in (event.plan_warnings or [])],
        "excluded_steps": event.plan_excluded_steps or [],
        "summary": {
            "total_steps": total or 0,
            "ai_steps": actor_counts.get(StepActor.AI, 0),
            "approval_steps": actor_counts.get(StepActor.APPROVAL_REQUIRED, 0),
            "manual_steps": actor_counts.get(StepActor.MANUAL, 0),
        },
        "base_revision": conversation.base_revision if conversation is not None else 0,
        "generation_readiness": (
            ai.planning_generation_readiness(draft, resume_state=resume_state).model_dump(mode="json")
            if resume_state is not None else None
        ),
    }
