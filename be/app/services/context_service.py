"""Jev 판단 오케스트레이션 — 판단 작업 생성, 분기별 도구 호출, 판단·할 일 후보 저장.

최종 전사·허용 채널 메시지가 들어오면 자동으로 판단 작업을 만든다. PM이 판단 API를
따로 부르지 않는다. 판단·검색·생성은 더미(meeting_judge_stub, context_tools_stub)다.

NONE 분기는 판단 기록만 남기고 검색·생성·할 일 도구를 부르지 않는다.
"""

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.models.meetings import Meeting, TranscriptSegment
from app.models.tasks import TaskSuggestion
from app.services import agent_job_service, context_tools_stub
from app.services.meeting_judge_stub import (
    STUB_MODEL_NAME,
    STUB_PROMPT_VERSION,
    judge_utterance_stub,
)

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


async def decide_meeting_segment(
    session: AsyncSession, *, meeting: Meeting, segment: TranscriptSegment
) -> tuple[AgentJob, ContextDecision]:
    """확정 전사 하나를 판단한다. 커밋은 호출하는 쪽이 한다."""
    job = await agent_job_service.create_job(
        session, club_id=meeting.club_id, kind=AgentJobKind.CONTEXT_DECISION
    )
    agent_job_service.start(session, job, AgentJobStage.DECIDING)
    judged = judge_utterance_stub(segment.text)

    kind = JudgeKind.NO_LOOKUP
    output: str | None = None
    citations: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] = []
    if judged.route == JudgeRoute.RAG:
        agent_job_service.set_stage(session, job, AgentJobStage.RETRIEVING)
        started = time.perf_counter()
        hits = await context_tools_stub.search_records(
            session, club_id=meeting.club_id, query=judged.question or segment.text
        )
        tool_calls.append(
            _tool_call(
                "records.search",
                started,
                input={"clubId": meeting.club_id, "query": judged.question},
                resultCount=len(hits),
            )
        )
        citations = [
            {
                "recordId": hit.record_id,
                "fileName": hit.file_name,
                "location": {"label": hit.location_label},
                "text": hit.text,
            }
            for hit in hits
        ]
        if hits:
            kind = JudgeKind.ANSWER
            output = context_tools_stub.answer_from_hits(hits)
        else:
            kind = JudgeKind.NOT_FOUND
    elif judged.route == JudgeRoute.LLM:
        agent_job_service.set_stage(session, job, AgentJobStage.GENERATING)
        started = time.perf_counter()
        output = context_tools_stub.generate_text(segment.text)
        tool_calls.append(_tool_call("llm.generate", started))
        kind = JudgeKind.ANSWER

    decision = ContextDecision(
        club_id=meeting.club_id,
        job_id=job.id,
        source_type=ContextSourceType.MEETING_TRANSCRIPT,
        meeting_id=meeting.id,
        sources=[{"sourceId": segment.id, "sourceVersion": segment.version}],
        status=ContextDecisionStatus.SUCCEEDED,
        route=judged.route,
        kind=kind,
        reason_summary=judged.reason,
        question=judged.question,
        output=output,
        citations=citations,
        tool_calls=tool_calls,
        model_version=STUB_MODEL_NAME,
        policy_version=POLICY_VERSION,
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
