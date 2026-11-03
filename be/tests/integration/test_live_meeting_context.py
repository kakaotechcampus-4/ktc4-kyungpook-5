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
        trace=SimpleNamespace(
            model="fixture-boundary", prompt_version="fixture-v1", judge_ms=1480, tool_calls=(),
        ),
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
        # trace 없이 실패하면 잰 판단 시간이 없다. 0으로 채우면 빠른 판단처럼 보인다
        assert decision.judge_ms is None
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


async def _saved_meeting_with_earlier_utterances(session, texts: list[str]) -> tuple[str, list[str]]:
    """확정 전사 여러 개를 순번대로 저장한다. 마지막이 판단할 발화다."""
    club = Club(name="판단 입력 저장 테스트")
    session.add(club)
    await session.flush()
    owner = Member(club_id=club.id, name="회의 운영진", role=MemberRole.OWNER)
    session.add(owner)
    await session.flush()
    meeting = await meeting_service.create_meeting(
        session, club_id=club.id, event_id=None, title="MT 준비",
        language="ko-KR", recording_consent_confirmed=True, created_by=owner.id,
    )
    segments = [
        TranscriptSegment(
            meeting_id=meeting.id, seq=seq, text=text, is_final=True, version=1,
            change_seq=seq, start_ms=(seq - 1) * 2000, end_ms=(seq - 1) * 2000 + 1500,
        )
        for seq, text in enumerate(texts, start=1)
    ]
    session.add_all(segments)
    meeting.transcript_cursor = len(texts)
    await session.commit()
    return meeting.id, [segment.id for segment in segments]


async def test_decision_keeps_judge_input_as_sent_even_after_earlier_transcript_is_edited(app_db, monkeypatch) -> None:
    sent: list[dict] = []

    async def judge(payload):
        sent.append(payload)
        return _no_lookup(payload)

    async def extract(payload):
        return []

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    texts = [
        "오늘 회의 시작할게요",
        "다음 달 MT 준비 얘기해 볼게요",
        "숙소는 작년이랑 같은 데로 하죠",
        "작년 숙소비 기억나는 사람?",
        "저도 잘…",
        "그때 얼마였지?",
    ]
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        meeting_id, segment_ids = await _saved_meeting_with_earlier_utterances(session, texts)
        _, decision = await _decide(session, meeting_id, segment_ids[-1])
        decision_id = decision.id
    # 판단 뒤 앞 발화의 전사를 고친다. version이 오르고 text가 덮어써진다
    async with factory() as session:
        edited = await session.get(TranscriptSegment, segment_ids[3])
        edited.version, edited.text = 2, "작년 숙박비 기억나는 사람?"
        await session.commit()
    async with factory() as session:
        decision = await session.get(ContextDecision, decision_id)
        request = ai.JudgeUtteranceRequest.model_validate(decision.judge_input)
        assert decision.judge_ms == 1480
        assert request.utterance.utterance_id == segment_ids[-1] and request.utterance.text == "그때 얼마였지?"
        # 앞 발화는 마지막 4개만, 오래된 것부터 넘겼다. 첫 발화는 빠진다
        assert [(item.utterance_id, item.version, item.text) for item in request.context] == [
            (segment_ids[seq], 1, texts[seq]) for seq in range(1, 5)
        ]
        assert request == ai.JudgeUtteranceRequest.model_validate(sent[0])


async def test_failed_judge_keeps_judge_time_from_error_trace(app_db, monkeypatch) -> None:
    async def judge(payload):
        error = ai.AITimeoutError("회의 판단이 제한 시간 안에 끝나지 않았습니다")
        error.trace = ai.JudgeTrace(model="fixture-boundary", prompt_version="fixture-v1", judge_ms=10004)
        raise error

    async def extract(payload):
        return []

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
        _, decision = await _decide(session, meeting_id, segment_id)
        decision_id = decision.id
    async with factory() as session:
        decision = await session.get(ContextDecision, decision_id)
        assert decision.route == JudgeRoute.ERROR
        assert decision.judge_ms == 10004
        assert ai.JudgeUtteranceRequest.model_validate(decision.judge_input).utterance.utterance_id == segment_id


# ── #249: 판단 결과는 추출을 기다리지 않고 보낸다 ─────────────────────────────


async def _process(meeting_id: str, segment_id: str) -> None:
    async with db_session.get_sessionmaker()() as session:
        await meeting_service.process_saved_segment(session, meeting_id=meeting_id, segment_id=segment_id)


async def test_judgment_is_sent_before_slow_extraction_finishes(app_db, monkeypatch) -> None:
    # 추출을 멈춰 둔 채로 판단 결과(judgment)가 먼저 화면에 가는지 본다.
    release_extraction, judgment_sent = asyncio.Event(), asyncio.Event()
    sent: list[dict] = []

    async def judge(payload):
        return _no_lookup(payload)

    async def extract(payload):
        await release_extraction.wait()
        return [_draft()]

    async def broadcast(meeting_id, message):
        sent.append(message)
        if message["type"] == "judgment":
            judgment_sent.set()

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    monkeypatch.setattr(meeting_service, "_broadcast", broadcast)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
    running = asyncio.create_task(_process(meeting_id, segment_id))
    try:
        await asyncio.wait_for(judgment_sent.wait(), timeout=3)
        judgment = next(message for message in sent if message["type"] == "judgment")
        assert (judgment["route"], judgment["kind"], judgment["status"]) == ("NONE", "NO_LOOKUP", "SUCCEEDED")
        # 판단 기록은 이미 커밋돼 다른 세션에서 보인다. 추출은 아직이라 작업은 RUNNING이고 후보가 없다
        async with factory() as reading:
            decision = await reading.get(ContextDecision, judgment["contextDecisionId"])
            assert decision.status == ContextDecisionStatus.SUCCEEDED
            assert (await reading.get(AgentJob, judgment["jobId"])).status == AgentJobStatus.RUNNING
            assert not list(await reading.scalars(select(TaskSuggestion).where(TaskSuggestion.decision_id == decision.id)))
    finally:
        release_extraction.set()
    await asyncio.wait_for(running, timeout=5)
    async with factory() as session:
        job = await session.get(AgentJob, judgment["jobId"])
        candidates = list(await session.scalars(
            select(TaskSuggestion).where(TaskSuggestion.decision_id == judgment["contextDecisionId"])
        ))
        assert job.status == AgentJobStatus.SUCCEEDED
        assert [candidate.id for candidate in candidates] == job.result["taskSuggestionIds"]
        assert len(candidates) == 1


async def test_extraction_only_failure_keeps_judgment_and_does_not_fail_processing(app_db, monkeypatch) -> None:
    # 추출만 실패하면 판단 결과는 그대로 가고, 처리 자체는 실패로 올리지 않는다.
    # 실패는 작업의 기능별 실패와 판단 기록의 PARTIAL로 남아 나중에 셀 수 있다.
    sent: list[dict] = []

    async def judge(payload):
        return _no_lookup(payload)

    async def extract(payload):
        raise ai.AITimeoutError("추출이 제한 시간 안에 끝나지 않았습니다")

    async def broadcast(meeting_id, message):
        sent.append(message)

    monkeypatch.setattr(meeting_ai_service, "judge", judge)
    monkeypatch.setattr(meeting_ai_service, "extract", extract)
    monkeypatch.setattr(meeting_service, "_broadcast", broadcast)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        _, meeting_id, segment_id = await _saved_transcript(session)
    await _process(meeting_id, segment_id)  # 예외가 올라오지 않아야 한다
    judgment = next(message for message in sent if message["type"] == "judgment")
    assert (judgment["route"], judgment["kind"]) == ("NONE", "NO_LOOKUP")
    async with factory() as session:
        decision = await session.get(ContextDecision, judgment["contextDecisionId"])
        job = await session.get(AgentJob, judgment["jobId"])
        assert decision.status == ContextDecisionStatus.PARTIAL
        assert (decision.route, decision.kind) == (JudgeRoute.NONE, JudgeKind.NO_LOOKUP)
        assert job.status == AgentJobStatus.FAILED
        assert job.error["features"] == [{"tool": "tasks.extract", "status": "FAILED", "code": "AITimeoutError"}]
