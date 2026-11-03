"""최신 공개 AI → PostgreSQL 판단/job → 인증된 GET 연결을 검증한다.

모델 객체만 가짜로 바꾸며 판단 facade·출처 구성·BE 검색 port는 실제 구현이다.
독립 후보 추출이 아직 없는 조합은 명시적인 부분 실패로 남긴다.
실모델 호출·음성 인식·Push 발송 검증은 아니다.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app import ai
from app.core.enums import MemberRole, RecordCategory, RecordFileType, RecordParseStatus
from app.core.security import hash_token
from app.db import session as db_session
from app.models.agent import AgentJob, ContextDecision
from app.models.auth import Account, Auth
from app.models.clubs import Club, Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.record_chunks import RecordChunk
from app.models.records import Record
from app.models.reminders import ConfirmedTask, TaskReminder
from app.models.tasks import TaskSuggestion
from app.services import context_service, meeting_service

pytestmark = [
    pytest.mark.db,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not hasattr(ai, "JudgeUtteranceRequest") or not hasattr(ai, "judge_utterance"),
        reason="requires AI public meeting boundary from develop6058a834 or newer",
    ),
]

VECTOR = (1.0,) + (0.0,) * (ai.EMBEDDING_DIMENSIONS - 1)
QUESTION = "2025 봄 MT 숙소비"
ANSWER = "2025 봄 MT 숙소비는 550,000원이다."


@pytest.fixture
async def case(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None,
) -> AsyncIterator[dict]:
    from app.ai.config import get_settings as get_ai_settings

    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("AI_MODEL", "bridge-model-fixture")
    get_ai_settings.cache_clear()
    tag = uuid.uuid4().hex
    token = f"bridge-test-{tag}"
    account = Account(email=f"bridge-{tag}@example.com")
    clubs = [Club(name=f"bridge-{tag}"), Club(name=f"outside-{tag}")]
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        session.add_all([account, *clubs])
        await session.flush()
        owner = Member(
            club_id=clubs[0].id, account_id=account.id, name="회장", role=MemberRole.OWNER
        )
        session.add(owner)
        expires = datetime.now(UTC) + timedelta(hours=1)
        session.add(Auth(
            account_id=account.id, access_token_hash=hash_token(token),
            access_token_expires_at=expires, refresh_token_hash=hash_token(token + "-refresh"),
            expires_at=expires,
        ))
        await session.flush()
        meeting = await meeting_service.create_meeting(
            session, club_id=clubs[0].id, event_id=None, title="실제 공개 경계 연결 검사",
            language="ko-KR", recording_consent_confirmed=True, created_by=owner.id,
        )
        segment = TranscriptSegment(
            meeting_id=meeting.id, seq=1, version=1, text="작년 MT 숙소비 얼마였지?",
            is_final=True, change_seq=1, start_ms=0, end_ms=1500,
        )
        session.add(segment)
        records = [Record(
            club_id=club.id, file_name=f"{'내' if index == 0 else '다른'} 조직 결과보고.csv",
            category=RecordCategory.EVENT_HISTORY, file_type=RecordFileType.CSV,
            storage_key=f"bridge/{tag}/{index}.csv", size=1,
            parse_status=RecordParseStatus.INDEXED,
        ) for index, club in enumerate(clubs)]
        session.add_all(records)
        await session.flush()
        session.add_all([RecordChunk(
            record_id=record.id, chunk_index=0,
            text="숙소비 550,000원" if index == 0 else "다른 조직의 비공개 금액 999,999원",
            location={"label": "2행 · 숙소비"}, block_indexes=[0], embedding=list(VECTOR),
        ) for index, record in enumerate(records)])
        await session.commit()
        data = {
            "club": clubs[0].id, "meeting": meeting.id, "segment": segment.id,
            "record": records[0].id, "fileName": records[0].file_name,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    try:
        yield data
    finally:
        async with factory() as session:
            await session.execute(delete(Club).where(Club.id.in_([club.id for club in clubs])))
            await session.execute(delete(Account).where(Account.id == account.id))
            await session.commit()
        get_ai_settings.cache_clear()
        await db_session.get_engine().dispose()


class ModelFixture:
    streaming = False
    use_responses_api = True

    def __init__(self, needs_lookup: bool, *, suggestions=None, lookup_error: bool = False):
        self.needs_lookup = needs_lookup
        self.suggestions = suggestions
        self.lookup_error = lookup_error
        self.calls: list[str] = []

    def with_structured_output(self, schema, *, method, include_raw):
        assert method == "json_schema" and include_raw is True
        fixture = self

        class Structured:
            async def ainvoke(self, messages):
                fixture.calls.append(schema.__name__)
                if schema.__name__ == "JudgeOutput":
                    if fixture.lookup_error:
                        raise ai.AIRetryableError("raw-sensitive-model-failure")
                    parsed = schema.model_validate({
                        "needs_lookup": fixture.needs_lookup, "query": QUESTION,
                    })
                elif schema.__name__ == "TaskExtractionResult":
                    request = json.loads(messages[1].content)
                    assert request["timezone"] == "Asia/Seoul"
                    assert request["occurred_at"] == "2030-10-19T10:00:00+09:00"
                    assert "민수" in request["utterance"] and request["context"] == []
                    assert fixture.suggestions is not None
                    parsed = schema.model_validate({"suggestions": fixture.suggestions})
                    for item in parsed.suggestions:
                        assert set(item.model_dump()) == {
                            "kind", "title", "description", "suggested_assignee",
                            "due_date", "due_at", "scheduled_at", "unresolved_fields",
                        }
                else:
                    assert schema.__name__ == "EvidenceAssessment"
                    prompt = "\n".join(str(message.content) for message in messages)
                    assert "숙소비 550,000원" in prompt
                    assert "다른 조직의 비공개 금액" not in prompt
                    parsed = schema.model_validate({
                        "sufficient": True, "retry_queries": [],
                        "facts": [{"content": ANSWER, "chunk_ids": ["c1"]}],
                        "not_found": [], "conflicts": [],
                    })
                return {"parsed": parsed, "parsing_error": None, "raw": None}

        return Structured()


class EmbeddingFixture:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def aembed_documents(self, texts):
        self.calls.append(texts)
        return [list(VECTOR) for _ in texts]


@pytest.mark.parametrize("needs_lookup", [True, False], ids=["rag-answer", "none"])
async def test_public_judge_records_keyword_persists_result_and_get_contract(
    client, case: dict, monkeypatch, needs_lookup: bool,
) -> None:
    from app.ai import llm
    from app.ai.features.meeting import lookup, nodes

    # 조회 성공과 아직 없는 독립 추출의 부분 실패를 별도로 고정한다.
    monkeypatch.delattr(ai, "TaskExtractionRequest", raising=False)
    model, embedding = ModelFixture(needs_lookup), EmbeddingFixture()
    monkeypatch.setattr(nodes, "get_judge_model", lambda: model)
    monkeypatch.setattr(lookup, "get_assess_model", lambda: model)
    monkeypatch.setattr(llm, "get_embeddings", lambda: embedding)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        meeting = await session.get(Meeting, case["meeting"])
        segment = await session.get(TranscriptSegment, case["segment"])
        job, decision = await context_service.decide_live_meeting_segment(
            session, meeting=meeting, segment=segment,
        )
        await session.commit()
        job_id, decision_id = job.id, decision.id

    job_response = client.get(f"/api/v1/agent-jobs/{job_id}", headers=case["headers"])
    assert job_response.status_code == 200, job_response.text
    job = job_response.json()["data"]
    assert job["status"] == "FAILED"
    assert job["result"] == {"contextDecisionId": decision_id, "taskSuggestionIds": []}
    assert job["error"]["features"] == [{
        "tool": "tasks.extract", "status": "FAILED", "code": "AI_PUBLIC_CONTRACT_UNAVAILABLE",
    }]
    url = f"/api/v1/clubs/{case['club']}/context-decisions"
    response = client.get(url + f"/{decision_id}", headers=case["headers"])
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["status"] == "PARTIAL" and result["meetingId"] == case["meeting"]
    assert result["sources"] == [{"sourceId": case["segment"], "sourceVersion": 1}]
    assert result["modelVersion"] == "bridge-model-fixture"
    if needs_lookup:
        assert (result["route"], result["kind"], result["question"]) == ("RAG", "ANSWER", QUESTION)
        assert result["output"] == ANSWER
        assert result["citations"] == [{
            "recordId": case["record"], "fileName": case["fileName"],
            "location": ai.SourceLocation(label="2행 · 숙소비").model_dump(mode="json"),
        }]
        assert model.calls == ["JudgeOutput", "EvidenceAssessment"]
        assert embedding.calls == [[QUESTION]]
    else:
        assert (result["route"], result["kind"]) == ("NONE", "NO_LOOKUP")
        assert result["question"] is None and result["output"] is None
        assert result["citations"] == []
        assert model.calls == ["JudgeOutput"] and embedding.calls == []
    listed = client.get(url, headers=case["headers"], params={"meetingId": case["meeting"]})
    assert listed.status_code == 200 and listed.json()["data"] == [result]
    # GET은 새 DB 세션이다. 결과가 메모리에만 남거나 후보/예약이 자동 생성되면 안 된다.
    async with factory() as session:
        saved_job = await session.get(AgentJob, job_id)
        saved_decision = await session.get(ContextDecision, decision_id)
        assert saved_job.result["contextDecisionId"] == saved_decision.id
        for table in (TaskSuggestion, ConfirmedTask, TaskReminder):
            assert await session.scalar(select(table.id).where(table.club_id == case["club"])) is None


@pytest.mark.skipif(
    not hasattr(ai, "TaskExtractionRequest") or not hasattr(ai, "extract_task_suggestions"),
    reason="requires AI public task extraction boundary from d28499f or newer",
)
@pytest.mark.parametrize("lookup_outcome", ["rag", "none", "error"])
async def test_public_extraction_persists_two_review_candidates_independently_of_lookup(
    client, case: dict, monkeypatch, lookup_outcome: str,
) -> None:
    from app.ai import llm
    from app.ai.features.meeting import lookup, nodes

    drafts = [
        {
            "kind": "TASK", "title": "자료 정리",
            "description": "원본 링크 정리\n운영진 검토 후 공유", "suggested_assignee": "민수",
            "due_date": "2030-10-23", "due_at": "2030-10-23T15:00:00+09:00",
            "scheduled_at": None, "unresolved_fields": ["recipientAccountIds", "reminderAt"],
        },
        {
            "kind": "SCHEDULE", "title": "운영 회의", "description": "장소는 나중에 확인",
            "suggested_assignee": None, "due_date": None, "due_at": None,
            "scheduled_at": "2030-10-24T14:00:00+09:00",
            "unresolved_fields": ["suggested_assignee", "recipientAccountIds", "reminderAt", "location"],
        },
    ]
    model = ModelFixture(
        lookup_outcome == "rag", suggestions=drafts, lookup_error=lookup_outcome == "error",
    )
    embedding = EmbeddingFixture()
    monkeypatch.setattr(nodes, "get_judge_model", lambda: model)
    monkeypatch.setattr(lookup, "get_assess_model", lambda: model)
    monkeypatch.setattr(llm, "get_chat_model", lambda: model)
    monkeypatch.setattr(llm, "get_embeddings", lambda: embedding)
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        meeting = await session.get(Meeting, case["meeting"])
        meeting.started_at = datetime(2030, 10, 19, 1, tzinfo=UTC)
        segment = await session.get(TranscriptSegment, case["segment"])
        segment.text = (
            "작년 MT 숙소비 얼마였지? 민수는 10월 23일 오후 3시까지 자료를 정리하고 "
            "10월 24일 오후 2시에 운영 회의를 합시다. 장소는 나중에 정합시다."
        )
        job, decision = await context_service.decide_live_meeting_segment(
            session, meeting=meeting, segment=segment,
        )
        await session.commit()
        job_id, decision_id = job.id, decision.id

    job_response = client.get(f"/api/v1/agent-jobs/{job_id}", headers=case["headers"])
    assert job_response.status_code == 200, job_response.text
    job = job_response.json()["data"]
    base = f"/api/v1/clubs/{case['club']}"
    decision_response = client.get(base + f"/context-decisions/{decision_id}", headers=case["headers"])
    assert decision_response.status_code == 200, decision_response.text
    result = decision_response.json()["data"]
    evidence = [{"sourceId": case["segment"], "sourceVersion": 1}]
    assert result["sources"] == evidence and result["meetingId"] == case["meeting"]
    assert {"tool": "tasks.extract", "status": "OK", "resultCount": 2} in result["toolCalls"]
    assert model.calls.count("TaskExtractionResult") == model.calls.count("JudgeOutput") == 1
    if lookup_outcome == "error":
        assert job["status"] == "FAILED" and result["status"] == "PARTIAL"
        assert (result["route"], result["kind"]) == ("ERROR", "FAILED")
        assert result["output"] is None and result["citations"] is None
        assert job["error"]["features"] == [{
            "tool": "meeting.lookup", "status": "FAILED", "code": "AIRetryableError",
        }]
        assert "raw-sensitive" not in str(job) + str(result)
    else:
        assert job["status"] == result["status"] == "SUCCEEDED"
        assert job["error"] is None
        if lookup_outcome == "rag":
            assert (result["route"], result["kind"], result["output"]) == ("RAG", "ANSWER", ANSWER)
            assert {item["recordId"] for item in result["citations"]} == {case["record"]}
        else:
            assert (result["route"], result["kind"]) == ("NONE", "NO_LOOKUP")
            assert result["output"] is None and result["citations"] == []
    if lookup_outcome == "rag":
        assert model.calls.count("EvidenceAssessment") == 1 and embedding.calls == [[QUESTION]]
    else:
        assert "EvidenceAssessment" not in model.calls and embedding.calls == []

    response = client.get(
        base + "/task-suggestions", headers=case["headers"], params={"meetingId": case["meeting"]},
    )
    assert response.status_code == 200, response.text
    suggestions = response.json()["data"]
    assert len(suggestions) == 2
    assert set(job["result"]["taskSuggestionIds"]) == {item["id"] for item in suggestions}
    assert job["result"]["contextDecisionId"] == decision_id
    by_title = {item["title"]: item for item in suggestions}
    for draft in drafts:
        item = by_title[draft["title"]]
        assert item["decisionId"] == decision_id and item["evidence"] == evidence
        assert item["kind"] == draft["kind"] and item["description"] == draft["description"]
        assert item["suggestedAssignee"] == draft["suggested_assignee"]
        assert item["dueDate"] == draft["due_date"]
        assert item["unresolvedFields"] == draft["unresolved_fields"]
        assert item["status"] == "PROPOSED" and item["version"] == 1
        assert item["acceptedBy"] is None and item["acceptedAt"] is None
        for public_name, draft_name in (("dueAt", "due_at"), ("scheduledAt", "scheduled_at")):
            if draft[draft_name] is None:
                assert item[public_name] is None
            else:
                actual = datetime.fromisoformat(item[public_name].replace("Z", "+00:00"))
                assert actual.tzinfo is not None
                assert actual == datetime.fromisoformat(draft[draft_name])
        detail = client.get(base + f"/task-suggestions/{item['id']}", headers=case["headers"])
        assert detail.status_code == 200 and detail.json()["data"] == item

    async with factory() as session:
        candidates = list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.club_id == case["club"])))
        assert len(candidates) == 2
        task = next(item for item in candidates if item.kind == "TASK")
        schedule = next(item for item in candidates if item.kind == "SCHEDULE")
        assert task.due_at.tzinfo is not None and task.due_at == datetime.fromisoformat(drafts[0]["due_at"])
        assert schedule.scheduled_at.tzinfo is not None
        assert schedule.scheduled_at == datetime.fromisoformat(drafts[1]["scheduled_at"])
        for table in (ConfirmedTask, TaskReminder):
            assert await session.scalar(select(table.id).where(table.club_id == case["club"])) is None
