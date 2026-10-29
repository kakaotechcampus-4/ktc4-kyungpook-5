"""Jev 판단 오케스트레이션 — 판단 작업 생성, 분기별 도구 호출, 판단·할 일 후보 저장.

실제 WS는 decide_live_meeting_segment에서 공개 AI의 조회와 후보 추출을 독립 호출한다.
이전 decide_meeting_segment/Discord 경로는 개발 fixture이고 실제 AI 결과가 아니다.
"""

import asyncio
import time
from datetime import timedelta
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
from app.services import meeting_ai_service
from app.services.meeting_judge_stub import (
    STUB_MODEL_NAME,
    STUB_PROMPT_VERSION,
    judge_utterance_stub,
)

POLICY_VERSION = f"{STUB_PROMPT_VERSION}+{context_tools_stub.STUB_TOOLS_VERSION}"
# Discord 판단에 함께 보는 앞 메시지 수(이번 메시지 포함).
DISCORD_CONTEXT_WINDOW = 5


async def decide_live_meeting_segment(
    session: AsyncSession, *, meeting: Meeting, segment: TranscriptSegment
) -> tuple[AgentJob, ContextDecision]:
    """실제 WS 전사 경로. 자료 조회와 후보 추출은 서로의 분기로 막지 않는다."""
    job = await agent_job_service.create_job(
        session, club_id=meeting.club_id, kind=AgentJobKind.CONTEXT_DECISION
    )
    agent_job_service.start(session, job, AgentJobStage.DECIDING)
    earlier = list(await session.scalars(
        select(TranscriptSegment).where(
            TranscriptSegment.meeting_id == meeting.id,
            TranscriptSegment.seq < segment.seq, TranscriptSegment.is_final.is_(True),
            TranscriptSegment.text != "",
        ).order_by(TranscriptSegment.seq.desc()).limit(4)
    ))

    def utterance(item: TranscriptSegment) -> dict:
        return {
            "utterance_id": item.id, "seq": item.seq, "version": item.version,
            "text": item.text,
            "started_at": meeting.started_at + timedelta(milliseconds=item.start_ms or 0),
            "ended_at": meeting.started_at + timedelta(milliseconds=item.end_ms or item.start_ms or 0),
        }

    payload = {
        "meeting_id": meeting.id, "club_id": meeting.club_id,
        "utterance": utterance(segment), "context": [utterance(item) for item in reversed(earlier)],
    }
    source = {"sourceId": segment.id, "sourceVersion": segment.version}
    meeting_id, segment_id, source_version = meeting.id, segment.id, segment.version
    segment.decision_job_id = job.id
    # 전사·진행 job을 먼저 보존하고 모델 대기 중 DB 연결을 반납한다.
    await session.commit()
    judged, extracted = await asyncio.gather(
        meeting_ai_service.judge(payload), meeting_ai_service.extract(payload), return_exceptions=True,
    )
    tools: list[dict] = []
    failures: list[dict] = []
    for name, result in (("meeting.lookup", judged), ("tasks.extract", extracted)):
        if isinstance(result, BaseException):
            code = getattr(result, "code", None) or type(result).__name__
            failure = {"tool": name, "status": "FAILED", "code": code}
            tools.append(failure)
            failures.append(failure)
    lookup_ok = not isinstance(judged, BaseException)
    extraction_ok = not isinstance(extracted, BaseException)
    # Public result validates route/kind/source ids; never turn lookup failure into NONE.
    trace = judged.trace if lookup_ok else None
    if trace is not None:
        tools.extend(item.model_dump(mode="json") for item in trace.tool_calls)
    if extraction_ok:
        tools.append({"tool": "tasks.extract", "status": "OK", "resultCount": len(extracted)})
    status = ContextDecisionStatus.SUCCEEDED
    if failures:
        status = ContextDecisionStatus.PARTIAL if lookup_ok or extraction_ok else ContextDecisionStatus.FAILED
    current = await session.scalar(select(TranscriptSegment).where(
        TranscriptSegment.id == segment_id,
    ).with_for_update().execution_options(populate_existing=True))
    if current.version != source_version:
        status = ContextDecisionStatus.STALE
    decision = ContextDecision(
        club_id=job.club_id, job_id=job.id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
        meeting_id=meeting_id, sources=[source], status=status,
        route=JudgeRoute(judged.route) if lookup_ok else JudgeRoute.ERROR,
        kind=JudgeKind(judged.kind) if lookup_ok else JudgeKind.FAILED,
        question=judged.question if lookup_ok else None,
        output=judged.answer if lookup_ok else None,
        citations=None,
        reason_summary=None if not failures else "일부 AI 처리를 완료하지 못했습니다. 기능별 오류를 확인해 주세요.",
        tool_calls=tools,
        model_version=trace.model if trace is not None else "unavailable",
        policy_version=trace.prompt_version if trace is not None else "unavailable",
    )
    # AI 계약은 snake_case지만 FE 저장 출처는 기존 camelCase를 유지한다.
    if lookup_ok:
        decision.citations = [
            {"recordId": source.record_id, "fileName": source.file_name,
             "location": source.location.model_dump(mode="json")}
            for source in judged.sources
        ]
    session.add(decision)
    await session.flush()
    suggestion_ids: list[str] = []
    if extraction_ok and status != ContextDecisionStatus.STALE:
        for draft in extracted:
            suggestion = TaskSuggestion(
                club_id=job.club_id, decision_id=decision.id,
                source_type=ContextSourceType.MEETING_TRANSCRIPT,
                title=draft.title, description=draft.description,
                suggested_assignee=draft.suggested_assignee,
                due_date=draft.due_date, kind=draft.kind, due_at=draft.due_at,
                scheduled_at=draft.scheduled_at, unresolved_fields=draft.unresolved_fields,
                evidence=[source],
            )
            session.add(suggestion)
            await session.flush()
            suggestion_ids.append(suggestion.id)
    result = {"contextDecisionId": decision.id, "taskSuggestionIds": suggestion_ids}
    if failures:
        job.result = result
        agent_job_service.fail(session, job, {"code": "MEETING_AI_FAILED", "features": failures})
    else:
        agent_job_service.succeed(session, job, result)
    if status != ContextDecisionStatus.STALE:
        current.decision_job_id = job.id
    return job, decision


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
            ContextDecision.status.in_([ContextDecisionStatus.SUCCEEDED, ContextDecisionStatus.PARTIAL]),
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
