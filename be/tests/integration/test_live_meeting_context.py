"""확정 전사 이후 자료 조회·후보 추출 독립성과 DB 원문 버전을 검증한다.

전사는 서비스/DB로 저장하고 공개 AI 호출 경계만 대체한다. 실모델·실음성
성능 또는 실제 기기 알림을 검증하는 테스트는 아니다.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app import ai
from app.core.enums import (
    AgentJobStatus, ContextDecisionStatus, JudgeKind, JudgeRoute,
    MemberRole, TaskSuggestionStatus,
)
from app.db import session as db_session
from app.models.agent import AgentJob, ContextDecision
from app.models.clubs import Club, Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.reminders import ConfirmedTask, TaskReminder
from app.models.tasks import TaskSuggestion
from app.services import context_service, meeting_ai_service, meeting_service

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None,
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def _saved_transcript(session) -> tuple[str, str, str]:
    club = Club(name="회의 공개 AI 경계 테스트")
    session.add(club)
    await session.flush()
    owner = Member(club_id=club.id, name="회의 운영진", role=MemberRole.OWNER)
    session.add(owner)
    await session.flush()
    meeting = await meeting_service.create_meeting(
        session, club_id=club.id, event_id=None, title="자료와 일정 후보",
        language="ko-KR", recording_consent_confirmed=True, created_by=owner.id,
    )
    segment = TranscriptSegment(
        meeting_id=meeting.id, seq=1, text="민수가 내일까지 행사 장소를 확인하자.",
        is_final=True, version=1, change_seq=1, start_ms=0, end_ms=1500,
    )
    meeting.transcript_cursor = 1
    session.add(segment)
    await session.commit()
    return club.id, meeting.id, segment.id


def _no_lookup(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        utterance_id=payload["utterance"]["utterance_id"],
        source_version=payload["utterance"]["version"], route="NONE", kind="NO_LOOKUP",
        question=None, answer=None, sources=(),
        trace=SimpleNamespace(model="fixture-boundary", prompt_version="fixture-v1", tool_calls=()),
    )


def _draft() -> meeting_ai_service.CandidateDraft:
    due_at = (datetime.now(UTC) + timedelta(days=1)).replace(microsecond=0)
    return meeting_ai_service.CandidateDraft(
        title="행사 장소 확인", kind="TASK", description="회의에서 나온 미확정 할 일",
        suggested_assignee="민수", due_date=due_at.date(), due_at=due_at,
        unresolved_fields=["recipientAccountIds", "reminderAt"],
    )


async def _decide(session, meeting_id: str, segment_id: str):
    meeting = await session.get(Meeting, meeting_id)
    segment = await session.get(TranscriptSegment, segment_id)
    result = await context_service.decide_live_meeting_segment(session, meeting=meeting, segment=segment)
    await session.commit()
    return result


async def test_none_lookup_still_persists_review_candidate_without_confirmation_or_reminder(app_db, monkeypatch) -> None:
    draft = _draft()

    async def judge(payload):
        return _no_lookup(payload)

    async def extract(payload):
        return [draft]

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        club_id, meeting_id, segment_id = await _saved_transcript(session)
        job, decision = await _decide(session, meeting_id, segment_id)
        job_id, decision_id = job.id, decision.id
    async with factory() as session:
        decision = await session.get(ContextDecision, decision_id)
        job = await session.get(AgentJob, job_id)
        assert decision.status == ContextDecisionStatus.SUCCEEDED
        assert decision.route == JudgeRoute.NONE and decision.kind == JudgeKind.NO_LOOKUP
        assert job.status == AgentJobStatus.SUCCEEDED
        suggestions = list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.decision_id == decision_id)))
        assert len(suggestions) == 1
        candidate = suggestions[0]
        assert candidate.status == TaskSuggestionStatus.PROPOSED
        assert candidate.title == draft.title and candidate.kind == "TASK"
        assert candidate.due_at == draft.due_at and candidate.suggested_assignee == "민수"
        assert candidate.unresolved_fields == ["recipientAccountIds", "reminderAt"]
        assert candidate.evidence == [{"sourceId": segment_id, "sourceVersion": 1}]
        assert job.result["taskSuggestionIds"] == [candidate.id]
        assert not list(await session.scalars(select(ConfirmedTask).where(ConfirmedTask.club_id == club_id)))
        assert not list(await session.scalars(select(TaskReminder).where(TaskReminder.club_id == club_id)))


async def test_lookup_error_preserves_extracted_candidate_and_explicit_partial_failure(app_db, monkeypatch) -> None:
    async def judge(payload):
        raise ai.AIError("raw-sensitive-error-must-not-be-stored")

    async def extract(payload):
        return [_draft()]

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
        job, decision = await _decide(session, meeting_id, segment_id)
        job_id, decision_id = job.id, decision.id
    async with factory() as session:
        job, decision = await session.get(AgentJob, job_id), await session.get(ContextDecision, decision_id)
        assert job.status == AgentJobStatus.FAILED
        assert decision.status == ContextDecisionStatus.PARTIAL
        assert decision.route == JudgeRoute.ERROR and decision.kind == JudgeKind.FAILED
        assert decision.output is None and decision.citations is None
        assert job.error == {"code": "MEETING_AI_FAILED", "features": [
            {"tool": "meeting.lookup", "status": "FAILED", "code": "AIError"}
        ]}
        assert "raw-sensitive" not in str(job.error) + str(decision.tool_calls) + str(decision.reason_summary)
        candidates = list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.decision_id == decision_id)))
        assert len(candidates) == 1 and candidates[0].id in job.result["taskSuggestionIds"]


async def test_missing_public_ai_contracts_persist_failure_without_fake_candidates(app_db, monkeypatch) -> None:
    # 실제 BE adapter의 미준비 처리. 내부 AI 모듈을 우회 import하지 않는다.
    for name in ("JudgeUtteranceRequest", "judge_utterance", "TaskExtractionRequest", "extract_task_suggestions"):
        monkeypatch.delattr(ai, name, raising=False)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
        job, decision = await _decide(session, meeting_id, segment_id)
        job_id, decision_id = job.id, decision.id
    async with factory() as session:
        job, decision = await session.get(AgentJob, job_id), await session.get(ContextDecision, decision_id)
        assert job.status == AgentJobStatus.FAILED
        assert decision.status == ContextDecisionStatus.FAILED
        assert decision.route == JudgeRoute.ERROR and decision.kind == JudgeKind.FAILED
        assert job.result["taskSuggestionIds"] == []
        assert {failure["code"] for failure in job.error["features"]} == {"AI_PUBLIC_CONTRACT_UNAVAILABLE"}
        assert len(job.error["features"]) == 2
        assert not list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.decision_id == decision_id)))


class FakePublicUtterance(BaseModel):
    utterance_id: str
    version: int


class FakePublicJudgeRequest(BaseModel):
    utterance: FakePublicUtterance


@pytest.mark.parametrize("wrong_id,wrong_version", [("other-segment", 1), ("expected-segment", 2)])
async def test_judge_adapter_rejects_wrong_source_id_or_version(monkeypatch, wrong_id, wrong_version) -> None:
    async def public_judge(request, *, records):
        assert records.club_id == "club-boundary"
        return SimpleNamespace(utterance_id=wrong_id, source_version=wrong_version)

    monkeypatch.setattr(ai, "JudgeUtteranceRequest", FakePublicJudgeRequest, raising=False)
    monkeypatch.setattr(ai, "judge_utterance", public_judge, raising=False)
    with pytest.raises(ai.AIInvalidResponseError, match="발화 ID·버전"):
        await meeting_ai_service.judge({
            "club_id": "club-boundary", "utterance": {"utterance_id": "expected-segment", "version": 1},
        })


async def test_edit_while_model_waits_marks_old_decision_stale_and_discards_candidate(app_db, monkeypatch) -> None:
    model_started, continue_model = asyncio.Event(), asyncio.Event()

    async def judge(payload):
        model_started.set()
        await continue_model.wait()
        return _no_lookup(payload)

    async def extract(payload):
        return [_draft()]

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
        running = asyncio.create_task(_decide(session, meeting_id, segment_id))
        try:
            await asyncio.wait_for(model_started.wait(), timeout=5)
            async with factory() as editing:
                current = await editing.get(TranscriptSegment, segment_id)
                current.version = 2
                current.text = "수정된 전사: 담당자는 아직 정하지 않았다."
                current.decision_job_id = None
                await editing.commit()
        finally:
            continue_model.set()
        job, decision = await asyncio.wait_for(running, timeout=5)
        decision_id, job_id = decision.id, job.id
    async with factory() as session:
        decision = await session.get(ContextDecision, decision_id)
        job = await session.get(AgentJob, job_id)
        current = await session.get(TranscriptSegment, segment_id)
        assert decision.status == ContextDecisionStatus.STALE
        assert decision.sources == [{"sourceId": segment_id, "sourceVersion": 1}]
        assert current.version == 2 and current.decision_job_id is None
        assert job.result["taskSuggestionIds"] == []
        assert not list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.decision_id == decision_id)))
