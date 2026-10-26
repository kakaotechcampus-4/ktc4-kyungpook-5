"""작업 상태, Jev 판단 조회, mini 활동 snapshot·SSE 엔드포인트."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ensure_member, get_current_account, require_member
from app.core.enums import ContextSourceType
from app.core.exceptions import ValidationFailed
from app.db.session import get_session, get_sessionmaker
from app.models.agent import ActivityEvent, ContextDecision
from app.models.auth import Account
from app.models.clubs import Member
from app.schemas.agent import (
    ActivityConnectionOut,
    ActivityJobOut,
    ActivitySnapshotOut,
    AgentJobOut,
    ContextDecisionOut,
)
from app.schemas.common import Envelope
from app.services import activity_service, agent_job_service, context_service

router = APIRouter(prefix="/api/v1", tags=["agent"])

# 새 이벤트를 확인하는 간격과, 이벤트가 없을 때 연결 유지용 주석을 보내는 간격(초)
STREAM_POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0


def _decision_out(decision: ContextDecision) -> ContextDecisionOut:
    return ContextDecisionOut(
        id=decision.id,
        job_id=decision.job_id,
        source_type=decision.source_type,
        meeting_id=decision.meeting_id,
        connection_id=decision.discord_connection_id,
        sources=decision.sources,
        status=decision.status,
        route=decision.route,
        kind=decision.kind,
        reason_summary=decision.reason_summary,
        question=decision.question,
        output=decision.output,
        citations=decision.citations,
        tool_calls=decision.tool_calls,
        model_version=decision.model_version,
        policy_version=decision.policy_version,
        created_at=decision.created_at,
    )


@router.get("/agent-jobs/{job_id}", response_model=Envelope[AgentJobOut])
async def get_agent_job(
    job_id: str,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[AgentJobOut]:
    job = await agent_job_service.get_job(session, job_id=job_id)
    await ensure_member(session, club_id=job.club_id, account=account)
    return Envelope(data=AgentJobOut.model_validate(job))


@router.get(
    "/clubs/{club_id}/context-decisions",
    response_model=Envelope[list[ContextDecisionOut]],
)
async def list_context_decisions(
    club_id: str,
    source_type: ContextSourceType | None = Query(None, alias="sourceType"),
    meeting_id: str | None = Query(None, alias="meetingId"),
    connection_id: str | None = Query(None, alias="connectionId"),
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[ContextDecisionOut]]:
    decisions = await context_service.list_decisions(
        session,
        club_id=club_id,
        source_type=source_type,
        meeting_id=meeting_id,
        connection_id=connection_id,
    )
    return Envelope(data=[_decision_out(decision) for decision in decisions])


@router.get(
    "/clubs/{club_id}/context-decisions/{decision_id}",
    response_model=Envelope[ContextDecisionOut],
)
async def get_context_decision(
    club_id: str,
    decision_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ContextDecisionOut]:
    decision = await context_service.get_decision(
        session, club_id=club_id, decision_id=decision_id
    )
    return Envelope(data=_decision_out(decision))


@router.get("/clubs/{club_id}/activity", response_model=Envelope[ActivitySnapshotOut])
async def get_activity(
    club_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ActivitySnapshotOut]:
    cursor, state, jobs, connections, proposed = await activity_service.snapshot(
        session, club_id=club_id
    )
    return Envelope(
        data=ActivitySnapshotOut(
            cursor=str(cursor),
            character_state=state,
            jobs=[ActivityJobOut.model_validate(job) for job in jobs],
            connections=[
                ActivityConnectionOut.model_validate(connection)
                for connection in connections
            ],
            proposed_task_count=proposed,
        )
    )


def _sse(event: ActivityEvent) -> str:
    data = {
        "clubId": event.club_id,
        "jobId": event.job_id,
        "kind": event.kind.value,
        "stage": event.stage.value if event.stage else None,
        "status": event.status.value,
        "timestamp": event.created_at.isoformat().replace("+00:00", "Z"),
    }
    return f"id: {event.id}\nevent: activity\ndata: {json.dumps(data)}\n\n"


@router.get("/clubs/{club_id}/activity/stream")
async def stream_activity(
    club_id: str,
    request: Request,
    authorization: str | None = Header(None),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Last-Event-ID 다음 이벤트부터 보낸다. 헤더가 없으면 지금부터 생기는 이벤트만.

    연결이 끊겨도 작업 실패가 아니다. 확정 상태는 agent-jobs·snapshot으로 다시 본다.
    get_session 의존성을 쓰지 않는다 — 스트림이 열려 있는 동안 DB 연결을 붙잡지 않도록
    인증도 짧은 세션에서 끝낸다.
    """
    if last_event_id is not None and not last_event_id.isdigit():
        raise ValidationFailed({"Last-Event-ID": "숫자 cursor여야 합니다."})
    async with get_sessionmaker()() as session:
        account = await get_current_account(authorization=authorization, session=session)
        await ensure_member(session, club_id=club_id, account=account)
        if last_event_id is None:
            start = await activity_service.latest_cursor(session, club_id=club_id)
        else:
            start = int(last_event_id)

    async def events() -> AsyncIterator[str]:
        cursor = start
        idle = 0.0
        while not await request.is_disconnected():
            # 요청 세션을 스트림 내내 붙잡지 않도록 조회마다 새 세션을 연다.
            async with get_sessionmaker()() as session:
                batch = await activity_service.events_after(
                    session, club_id=club_id, cursor=cursor
                )
            for event in batch:
                cursor = event.id
                yield _sse(event)
            if batch:
                idle = 0.0
                continue
            await asyncio.sleep(STREAM_POLL_SECONDS)
            idle += STREAM_POLL_SECONDS
            if idle >= HEARTBEAT_SECONDS:
                idle = 0.0
                yield ": heartbeat\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
