"""Jev 판단 오케스트레이션 — 판단 작업 생성, 분기별 도구 호출, 판단·할 일 후보 저장.

최종 전사가 들어오면 자동으로 판단 작업을 만들고 app.ai.judge_utterance를 실제로
부른다(#141). Discord 메시지 판단은 아직 더미다(meeting_judge_stub 패턴 재사용,
#116 범위).

NONE 분기는 판단 기록만 남기고 검색·생성·할 일 도구를 부르지 않는다.
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.ai as ai
from app.core.enums import (
    AgentJobKind,
    AgentJobStage,
    ContextDecisionStatus,
    ContextSourceType,
    JudgeKind,
    JudgeRoute,
)
from app.core.exceptions import ApiError
from app.models.agent import AgentJob, ContextDecision
from app.models.discord import DiscordMessage
from app.models.events import Event
from app.models.meetings import Meeting, TranscriptSegment
from app.models.tasks import TaskSuggestion
from app.services import agent_job_service, context_tools_stub
from app.services.meeting_judge_stub import STUB_MODEL_NAME, STUB_PROMPT_VERSION
from app.services.record_search_port import DbRecordSearchPort

POLICY_VERSION = f"{STUB_PROMPT_VERSION}+{context_tools_stub.STUB_TOOLS_VERSION}"
# Discord 판단에 함께 보는 앞 메시지 수(이번 메시지 포함).
DISCORD_CONTEXT_WINDOW = 5


class ContextDecisionNotFound(ApiError):
    status_code = 404
    code = "CONTEXT_DECISION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 판단 기록을 찾을 수 없습니다.")


def _tool_call(tool: str, started: float, **extra: Any) -> dict[str, Any]:
    return {
        "tool": tool,
        "status": "OK",
        "durationMs": int((time.perf_counter() - started) * 1000),
        **extra,
    }


def _to_utterance(meeting: Meeting, segment: TranscriptSegment) -> "ai.MeetingUtterance":
    """회의 시작 시각 + 녹음 안 오프셋(ms) = 실제 말한 시각."""
    base = meeting.started_at or datetime.now(UTC)
    return ai.MeetingUtterance(
        utterance_id=segment.id,
        seq=segment.seq,
        version=segment.version,
        text=segment.text,
        started_at=base + timedelta(milliseconds=segment.start_ms or 0),
        ended_at=base + timedelta(milliseconds=segment.end_ms or 0),
    )


async def _previous_final_segments(
    session: AsyncSession, *, meeting_id: str, before_seq: int
) -> list[TranscriptSegment]:
    rows = await session.scalars(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.meeting_id == meeting_id,
            TranscriptSegment.is_final.is_(True),
            TranscriptSegment.seq < before_seq,
        )
        .order_by(TranscriptSegment.seq.desc())
        .limit(ai.MEETING_CONTEXT_UTTERANCES)
    )
    return list(reversed(list(rows)))


async def decide_meeting_segment(
    session: AsyncSession,
    *,
    meeting: Meeting,
    segment: TranscriptSegment,
    progress: "ai.MeetingProgressPort | None" = None,
) -> tuple[AgentJob, ContextDecision]:
    """확정 전사 하나를 판단한다. 커밋은 호출하는 쪽이 한다."""
    job = await agent_job_service.create_job(
        session, club_id=meeting.club_id, kind=AgentJobKind.CONTEXT_DECISION
    )
    agent_job_service.start(session, job, AgentJobStage.DECIDING)

    context_segments = await _previous_final_segments(
        session, meeting_id=meeting.id, before_seq=segment.seq
    )
    event: ai.MeetingEvent | None = None
    if meeting.event_id:
        linked_event = await session.get(Event, meeting.event_id)
        if linked_event is not None:
            event = ai.MeetingEvent(
                event_id=linked_event.id, title=linked_event.title,
                event_type=linked_event.event_type, start_date=linked_event.start_date,
            )

    request = ai.JudgeUtteranceRequest(
        meeting_id=meeting.id, club_id=meeting.club_id,
        utterance=_to_utterance(meeting, segment),
        context=tuple(_to_utterance(meeting, s) for s in context_segments),
        event=event,
    )

    try:
        result = await ai.judge_utterance(
            request, records=DbRecordSearchPort(session), progress=progress
        )
    except ai.AIError as error:
        decision = ContextDecision(
            club_id=meeting.club_id, job_id=job.id,
            source_type=ContextSourceType.MEETING_TRANSCRIPT, meeting_id=meeting.id,
            sources=[{"sourceId": segment.id, "sourceVersion": segment.version}],
            status=ContextDecisionStatus.FAILED,
            route=JudgeRoute.NONE, kind=JudgeKind.NO_LOOKUP,
            reason_summary=f"판단 실패: {type(error).__name__}",
            tool_calls=[],
            model_version=STUB_MODEL_NAME, policy_version=POLICY_VERSION,
        )
        session.add(decision)
        await session.flush()
        agent_job_service.fail(session, job, {"error": type(error).__name__})
        segment.decision_job_id = job.id
        return job, decision

    citations = [
        {"recordId": source.record_id, "fileName": source.file_name,
         "location": {"label": source.location.label}}
        for source in result.sources
    ]
    tool_calls = [
        {
            "tool": call.tool, "status": call.status, "durationMs": call.duration_ms,
            **({"resultCount": call.result_count} if call.result_count is not None else {}),
            **({"promptVersion": call.prompt_version} if call.prompt_version else {}),
        }
        for call in result.trace.tool_calls
    ]

    decision = ContextDecision(
        club_id=meeting.club_id,
        job_id=job.id,
        source_type=ContextSourceType.MEETING_TRANSCRIPT,
        meeting_id=meeting.id,
        sources=[{"sourceId": segment.id, "sourceVersion": segment.version}],
        status=ContextDecisionStatus.SUCCEEDED,
        # result.route/kind는 app.ai 쪽 Literal["RAG","NONE"] 문자열이다. DB 컬럼은
        # JudgeRoute/JudgeKind라 명시적으로 바꿔야 한다 — 안 그러면 커밋 전까지는
        # 그냥 str이라 decision.route.value 같은 접근에서 바로 터진다.
        route=JudgeRoute(result.route),
        kind=JudgeKind(result.kind),
        # 판단 이유까지 받으면 0.65초 느려져 실시간 경로에서는 받지 않는다(#111).
        # 회의가 끝난 뒤 #117에서 채운다.
        reason_summary=None,
        question=result.question,
        output=result.answer,
        citations=citations or None,
        tool_calls=tool_calls,
        model_version=result.trace.model,
        policy_version=result.trace.prompt_version,
    )
    session.add(decision)
    await session.flush()
    agent_job_service.succeed(session, job, {"contextDecisionId": decision.id})
    segment.decision_job_id = job.id
    return job, decision


async def mark_segment_decisions_stale(
    session: AsyncSession, *, meeting_id: str, segment_id: str
) -> None:
    """전사가 정정되면 이전 버전으로 한 판단을 최신 결과로 보여주지 않는다."""
    decisions = await session.scalars(
        select(ContextDecision).where(
            ContextDecision.meeting_id == meeting_id,
            ContextDecision.status == ContextDecisionStatus.SUCCEEDED,
        )
    )
    for decision in decisions:
        if any(source["sourceId"] == segment_id for source in decision.sources):
            decision.status = ContextDecisionStatus.STALE


async def decide_discord_message(
    session: AsyncSession, *, message: DiscordMessage
) -> tuple[AgentJob, ContextDecision]:
    """새 메시지와 같은 채널의 앞 메시지를 함께 보고 판단한다. 커밋은 호출하는 쪽이 한다."""
    job = await agent_job_service.create_job(
        session, club_id=message.club_id, kind=AgentJobKind.CONTEXT_DECISION
    )
    agent_job_service.start(session, job, AgentJobStage.DECIDING)

    window = list(
        await session.scalars(
            select(DiscordMessage)
            .where(
                DiscordMessage.connection_id == message.connection_id,
                DiscordMessage.channel_id == message.channel_id,
                DiscordMessage.content.is_not(None),
                DiscordMessage.posted_at <= message.posted_at,
            )
            .order_by(DiscordMessage.posted_at.desc())
            .limit(DISCORD_CONTEXT_WINDOW)
        )
    )
    window.reverse()
    sources = [
        {"sourceId": item.id, "messageId": item.message_id, "sourceVersion": item.version}
        for item in window
    ]

    route, reason = context_tools_stub.judge_discord_window(message.content or "")
    tool_calls: list[dict[str, Any]] = []
    output: str | None = None
    task: TaskSuggestion | None = None
    if route == JudgeRoute.LLM:
        agent_job_service.set_stage(session, job, AgentJobStage.DETECTING_TASK)
        started = time.perf_counter()
        title, description = context_tools_stub.draft_task(
            message.content or "", [item.content or "" for item in window]
        )
        tool_calls.append(_tool_call("tasks.detect", started, resultCount=1))
        output = title
        task = TaskSuggestion(
            club_id=message.club_id,
            source_type=ContextSourceType.DISCORD_MESSAGE,
            title=title,
            description=description,
            evidence=sources,
        )

    decision = ContextDecision(
        club_id=message.club_id,
        job_id=job.id,
        source_type=ContextSourceType.DISCORD_MESSAGE,
        discord_connection_id=message.connection_id,
        sources=sources,
        status=ContextDecisionStatus.SUCCEEDED,
        route=route,
        kind=JudgeKind.ANSWER if task else JudgeKind.NO_LOOKUP,
        reason_summary=reason,
        output=output,
        tool_calls=tool_calls,
        model_version=STUB_MODEL_NAME,
        policy_version=POLICY_VERSION,
    )
    session.add(decision)
    await session.flush()
    result: dict[str, Any] = {"contextDecisionId": decision.id}
    if task is not None:
        task.decision_id = decision.id
        session.add(task)
        await session.flush()
        result["taskSuggestionIds"] = [task.id]
    agent_job_service.succeed(session, job, result)
    return job, decision


async def get_decision(
    session: AsyncSession, *, club_id: str, decision_id: str
) -> ContextDecision:
    decision = await session.get(ContextDecision, decision_id)
    if decision is None or decision.club_id != club_id:
        raise ContextDecisionNotFound()
    return decision


async def list_decisions(
    session: AsyncSession,
    *,
    club_id: str,
    source_type: ContextSourceType | None,
    meeting_id: str | None,
    connection_id: str | None,
) -> list[ContextDecision]:
    query = select(ContextDecision).where(ContextDecision.club_id == club_id)
    if source_type is not None:
        query = query.where(ContextDecision.source_type == source_type)
    if meeting_id is not None:
        query = query.where(ContextDecision.meeting_id == meeting_id)
    if connection_id is not None:
        query = query.where(ContextDecision.discord_connection_id == connection_id)
    return list(await session.scalars(query.order_by(ContextDecision.created_at)))
