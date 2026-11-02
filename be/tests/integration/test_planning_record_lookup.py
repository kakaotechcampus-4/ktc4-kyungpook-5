"""HTTP→공개 P1→실제 pgvector→상태 복원. 모델·임베딩만 고정한다 (#235, #236)."""

from collections import deque
from functools import partial
import json
import uuid

from alembic import command
from langchain_core.messages import AIMessage
import anyio
import pytest
from sqlalchemy import select

import app.ai as ai
from app.ai.features.planning import public_workflow as workflow
from app.ai.features.planning.agent import graph
from app.ai.features.planning.agent.nodes import SEARCH_TOOL_NAME, TOOL_NAME
from app.ai.features.planning.agent.record_tool import search_past_events
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.schemas import EvidenceAssessment, SearchQueries
from app.ai.tests.test_plan_generation_graph import Model, composition
from app.core.enums import RecordCategory, RecordFileType, RecordParseStatus
from app.db import session as db_session
from app.models.chat import Conversation
from app.models.record_chunks import RecordChunk
from app.models.records import Record

pytestmark = [pytest.mark.db, pytest.mark.anyio]
VECTOR = (1.0,) + (0.0,) * (ai.EMBEDDING_DIMENSIONS - 1)
SETUP_TEXT = "MT를 준비해. 참가비는 25000원으로 잡고 날짜와 인원과 장소는 미정이야."


def call(name, args, id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def change(field, value, message_id, quote):
    return {"op": "SET", "change": {"field": field, "value": value},
            "status": "specified", "evidence": {"message_id": message_id, "quote": quote}}


class Models:
    def __init__(self):
        self.responses = deque()
        self.agent_calls = 0
        self.search_calls = 0
        self.embed_error = None
        self.assessment = EvidenceAssessment(sufficient=True, retry_queries=[],
            facts=[{"content": "2025 봄 MT 참가비 45000원", "chunk_ids": ["c1"]}],
            not_found=[], conflicts=[])

    async def agent(self, messages, *, search_enabled, **kwargs):
        assert search_enabled, "제품 P1에 실제 검색 port가 주입돼야 한다"
        self.agent_calls += 1
        return self.responses.popleft()

    async def embed(self, texts):
        self.search_calls += 1
        if self.embed_error:
            raise self.embed_error
        return [VECTOR for _ in texts]

    async def structured(self, messages, schema):
        if schema is SearchQueries:
            return SearchQueries(queries=["2025 봄 MT 참가비"])
        assert schema is EvidenceAssessment
        # 후보 선택은 고정하지만 청크·범위·원문 위치는 실제 DB 결과를 사용한다.
        data = messages[-1].content
        assert "45000" in data
        assert "OTHER_CLUB" not in data and "UNINDEXED" not in data
        return self.assessment

    def lookup(self, suffix="1"):
        self.responses.extend([call(SEARCH_TOOL_NAME, {"query": "2025 봄 MT 참가비"}, "s-" + suffix),
                               AIMessage(content="2025 봄 MT 참가비는 45000원이었어요.")])


@pytest.fixture
async def context(migrated_db_url, monkeypatch, clear_db_caches, tmp_path):
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    models = Models()
    monkeypatch.setattr(graph, "call_agent_model", models.agent)
    monkeypatch.setattr(workflow, "search_past_events",
        partial(search_past_events, embed=models.embed, invoke=models.structured))

    async def index_embed(texts):
        return [VECTOR for _ in texts]

    monkeypatch.setattr(ai, "index_record", partial(index_record_chunks, embed=index_embed))
    yield models
    await db_session.get_engine().dispose()


def owner(client):
    email = f"p1-rag-{uuid.uuid4().hex}@example.com"
    response = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "PmTest-2027!", "name": "P1 기록 검증"})
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "PmTest-2027!"})
    headers = {"Authorization": "Bearer " + login.json()["data"]["accessToken"]}
    club = client.post("/api/v1/clubs", headers=headers, json={"name": "P1 과거 기록"})
    assert club.status_code == 201, club.text
    return headers, club.json()["data"]["id"]


def create_event(client, headers, club_id):
    response = client.post("/api/v1/events", headers=headers, json={"clubId": club_id})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def chat(client, headers, event_id, revision, message_id, text, key=None):
    auth = headers | ({"Idempotency-Key": key} if key else {})
    response = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=auth,
        json={"messageId": message_id, "message": text, "baseRevision": revision})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def setup(client, models):
    headers, club_id = owner(client)
    event_id = create_event(client, headers, club_id)
    models.responses.extend([
        call(TOOL_NAME, {"changes": [change("event_type", "MT", "u-setup", SETUP_TEXT),
              change("fee_per_person", 25000, "u-setup", SETUP_TEXT)],
            "defer_topics": [{"topic": topic, "evidence": {"message_id": "u-setup", "quote": SETUP_TEXT}}
                             for topic in ("dates", "headcount", "location")]}, "setup"),
        AIMessage(content="참가비는 25000원으로 잡았어요."),
    ])
    initial = chat(client, headers, event_id, 0, "u-setup", SETUP_TEXT)
    assert initial["draft"]["conditions"]["feePerPerson"] == 25000
    assert initial["generationReadiness"]["canGenerate"]
    return headers, club_id, event_id


def upload(client, headers, club_id, event_id, marker="참가비 45000"):
    response = client.post("/api/v1/records", headers=headers,
        data={"clubId": club_id, "eventId": event_id, "category": "ETC"},
        files={"file": ("2025 봄 MT.csv", f"항목,내용\n참가비,{marker}\n".encode(), "text/csv")})
    assert response.status_code == 201, response.text
    assert response.json()["data"]["parseStatus"] == "INDEXED"
    return response.json()["data"]["id"]


def screen(client, headers, event_id):
    response = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_real_scope_lookup_resume_accept_and_button_sources(client, context, monkeypatch):
    models = context
    headers, club_id, event_id = setup(client, models)
    past_event_id = create_event(client, headers, club_id)
    record_id = upload(client, headers, club_id, past_event_id)
    outside_headers, outside_club = owner(client)
    outside_event = create_event(client, outside_headers, outside_club)
    upload(client, outside_headers, outside_club, outside_event, "OTHER_CLUB 99999")
    async with db_session.get_sessionmaker()() as session:
        unready = Record(club_id=club_id, file_name="미색인.csv", file_type=RecordFileType.CSV,
            category=RecordCategory.ETC, storage_key="fixture", size=1,
            parse_status=RecordParseStatus.COMPLETED, parse_result={"blocks": []})
        session.add(unready)
        await session.flush()
        session.add(RecordChunk(record_id=unready.id, chunk_index=0, text="UNINDEXED 88888",
            location={"label": "2행"}, block_indexes=[0], embedding=list(VECTOR)))
        await session.commit()

    assert screen(client, headers, event_id)["lastRecordLookup"] is None
    models.lookup()
    key = str(uuid.uuid4())
    found = chat(client, headers, event_id, 1, "u-search", "2025 봄 MT 참가비는?", key)
    lookup = found["recordLookup"]
    assert lookup["status"] == "available"
    assert found["draft"]["conditions"]["feePerPerson"] == 25000
    sources = lookup["result"]["facts"][0]["sources"]
    assert sources == [{"recordId": record_id, "fileName": "2025 봄 MT.csv", "location": {"label": "2행"}}]
    calls = models.agent_calls, models.search_calls
    assert chat(client, headers, event_id, 1, "u-search", "2025 봄 MT 참가비는?", key) == found
    assert screen(client, headers, event_id)["lastRecordLookup"] == lookup
    assert (models.agent_calls, models.search_calls) == calls

    # 현재 조건 변경은 검색과 분리하고, 새 DB 세션에서 복원된 Tool 이력을 읽는다.
    models.responses.extend([
        call(TOOL_NAME, {"changes": [change("fee_per_person", 45000, "u-accept", "올해도 그 금액으로 하자")]}, "accept"),
        AIMessage(content="올해 참가비를 45000원으로 반영했어요."),
    ])
    accepted = chat(client, headers, event_id, 2, "u-accept", "올해도 그 금액으로 하자")
    assert accepted["draft"]["conditions"]["feePerPerson"] == 45000
    assert accepted["recordLookup"] is None
    assert screen(client, headers, event_id)["lastRecordLookup"] == lookup

    generation_inputs = []
    async def generate(request):
        generation_inputs.append(request)
        return await run_plan_generation(request, invoke=Model(composition(assumptions=[{
            "content": "과거 행사 준비 경험을 참고한다", "fact_ids": ["f1"]}])))

    monkeypatch.setattr(workflow, "run_plan_generation", generate)
    response = client.post(f"/api/v1/events/{event_id}/plan/generate", headers=headers,
        json={"baseRevision": 3, "useCurrentConditions": False})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["generationResult"]["status"] == "generated"
    assert generation_inputs[0].reference_facts[0].sources[0].record_id == record_id
    assert models.search_calls == calls[1]  # 버튼과 조회 복원은 재검색하지 않는다.
    assert screen(client, headers, event_id)["lastRecordLookup"] == lookup
    async with db_session.get_sessionmaker()() as session:
        conversation = await session.scalar(select(Conversation).where(Conversation.event_id == event_id))
        restored = ai.parse_resume_state(json.dumps(conversation.resume_state))
        assert restored.payload.generation.preview.assumptions[0].sources[0].record_id == record_id


@pytest.mark.parametrize("outcome", ["not_found", "failed", "conflict"])
async def test_new_lookup_replaces_previous_success_without_changing_conditions(client, context, outcome):
    models = context
    headers, club_id, event_id = setup(client, models)
    upload(client, headers, club_id, event_id)
    models.lookup()
    first = chat(client, headers, event_id, 1, "u-first", "작년 참가비는?")
    assert first["recordLookup"]["status"] == "available"
    if outcome == "failed":
        models.embed_error = ai.AITimeoutError("private-provider-detail")
    elif outcome == "not_found":
        models.assessment = EvidenceAssessment(sufficient=False, retry_queries=[], facts=[],
            not_found=["질문에 답할 근거"], conflicts=[])
    else:
        models.assessment = EvidenceAssessment(sufficient=True, retry_queries=[], facts=[],
            not_found=["숙소비 세부 내역"], conflicts=[{"description": "참가비 차이", "values": [
                {"content": "자료의 값 45000원", "chunk_ids": ["c1"]},
                {"content": "자료의 값 40000원", "chunk_ids": ["c1"]}]}])
    models.lookup("2")
    latest = chat(client, headers, event_id, 2, "u-next", "새 자료를 확인해줘")
    lookup = latest["recordLookup"]
    assert lookup["status"] == ("available" if outcome == "conflict" else outcome)
    assert latest["draft"]["conditions"]["feePerPerson"] == 25000
    assert screen(client, headers, event_id)["lastRecordLookup"] == lookup
    if outcome == "conflict":
        assert lookup["result"]["notFound"] == ["숙소비 세부 내역"]
        assert len(lookup["result"]["conflicts"][0]["values"]) == 2
    if outcome == "failed":
        assert lookup["result"] is None
        assert "private-provider-detail" not in json.dumps(latest)


async def test_empty_store_and_unauthorized_or_stale_requests(client, context):
    models = context
    headers, club_id, event_id = setup(client, models)
    models.lookup()
    empty = chat(client, headers, event_id, 1, "u-empty", "작년 참가비는?")
    assert empty["recordLookup"]["status"] == "not_found"
    assert empty["recordLookup"]["result"]["facts"] == []
    assert screen(client, headers, event_id)["lastRecordLookup"] == empty["recordLookup"]
    calls = models.agent_calls
    other_headers, _ = owner(client)
    denied = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=other_headers,
        json={"baseRevision": 2, "messageId": "u-denied", "message": "검색해줘"})
    assert denied.status_code in {403, 404}
    stale = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=headers,
        json={"baseRevision": 0, "messageId": "u-stale", "message": "검색해줘"})
    assert stale.status_code == 409
    assert models.agent_calls == calls


async def test_full_ai_failure_preserves_state_and_last_lookup(client, context, monkeypatch):
    models = context
    headers, club_id, event_id = setup(client, models)
    upload(client, headers, club_id, event_id)
    models.lookup()
    chat(client, headers, event_id, 1, "u-good", "작년 참가비는?")
    before = screen(client, headers, event_id)
    async with db_session.get_sessionmaker()() as session:
        row = await session.scalar(select(Conversation).where(Conversation.event_id == event_id))
        state_before = row.resume_state
    async def broken_model(*args, **kwargs):
        raise ai.AITimeoutError("private-provider-detail")
    # 실제 공개 P1은 그대로 두고 대화 모델만 실패시킨다.
    monkeypatch.setattr(graph, "call_agent_model", broken_model)
    response = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=headers,
        json={"baseRevision": 2, "messageId": "u-fail", "message": "다시 찾아줘"})
    assert response.status_code == 503
    assert screen(client, headers, event_id) == before
    async with db_session.get_sessionmaker()() as session:
        row = await session.scalar(select(Conversation).where(Conversation.event_id == event_id))
        assert row.resume_state == state_before


async def test_condition_change_survives_retryable_lookup_failure(client, context):
    models = context
    headers, _, event_id = setup(client, models)
    models.embed_error = ai.AITimeoutError("private-provider-detail")
    text = "인원은 40명으로 하고 작년 참가비도 찾아줘"
    models.responses.extend([
        call(TOOL_NAME, {"changes": [change("headcount", 40, "u-mixed", text)]}, "mixed-change"),
        call(SEARCH_TOOL_NAME, {"query": "2025 봄 MT 참가비"}, "mixed-search"),
        AIMessage(content="40명으로 반영했지만 기록 검색은 실패했어요."),
    ])
    result = chat(client, headers, event_id, 1, "u-mixed", text)
    assert result["recordLookup"]["status"] == "failed"
    restored = screen(client, headers, event_id)
    assert restored["draft"]["conditions"]["headcount"] == 40
    assert restored["draft"]["conditions"]["feePerPerson"] == 25000
    assert restored["lastRecordLookup"] == result["recordLookup"]


async def test_configuration_failure_does_not_become_not_found(client, context):
    models = context
    headers, _, event_id = setup(client, models)
    before = screen(client, headers, event_id)
    models.embed_error = ai.AIConfigError("private-provider-detail")
    models.lookup()
    response = client.post(f"/api/v1/events/{event_id}/plan/chat", headers=headers,
        json={"baseRevision": 1, "messageId": "u-config", "message": "작년 참가비는?"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "AI_MISCONFIGURED"
    assert "private-provider-detail" not in response.text
    assert screen(client, headers, event_id) == before


async def test_lookup_migration_preserves_existing_conversation(client, context, alembic_cfg):
    headers, _, event_id = setup(client, context)
    async with db_session.get_sessionmaker()() as session:
        row = await session.scalar(select(Conversation).where(Conversation.event_id == event_id))
        state_before, revision = row.resume_state, row.base_revision
    # 추가 전부터 있던 대화의 상태·버전은 유지하고 새 조회 필드만 null로 만든다.
    await db_session.get_engine().dispose()
    try:
        await anyio.to_thread.run_sync(partial(command.downgrade, alembic_cfg, "20261102_event_cancel_tasks"))
        await anyio.to_thread.run_sync(partial(command.upgrade, alembic_cfg, "head"))
        async with db_session.get_sessionmaker()() as session:
            row = await session.scalar(select(Conversation).where(Conversation.event_id == event_id))
            assert row.resume_state == state_before and row.base_revision == revision
            assert row.last_record_lookup is None
    finally:
        await anyio.to_thread.run_sync(partial(command.upgrade, alembic_cfg, "head"))
