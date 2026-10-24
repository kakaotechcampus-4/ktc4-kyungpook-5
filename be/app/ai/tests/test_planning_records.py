"""계획 → 실제 retrieval 연결을 검사한다. 외부 모델·임베딩·저장소만 대체한다."""

import asyncio
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.ai.contracts import RecordSource, SourceLocation
from app.ai.errors import AIInvalidResponseError, AITimeoutError
from app.ai.features.planning.records import build_record_search_request, search_planning_records
from app.ai.features.planning.schemas import PlanningRecordSearchInput
from app.ai.features.retrieval.schemas import EvidenceAssessment, SearchQueries
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.ai.ports import RetrievedChunk
from app.core.enums import RecordCategory


def make_request(**changes):
    return PlanningRecordSearchInput.model_validate({
        "club_id": "club-1", "planning_event_id": "event-2026",
        "request_id": "turn-7", "base_version": 3,
        "query": "작년 MT 장소와 교통비", "reference_date": "2026-10-23",
        "conditions": {"event_type": "MT", "headcount": 40}, **changes,
    })


class Port:
    def __init__(self, chunks=(), error=None):
        self.chunks = chunks
        self.error = error
        self.calls = []

    async def search_chunks(self, query):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.chunks


async def embed(texts):
    return [(1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1) for _ in texts]


class Model:
    def __init__(self, assessment=None):
        self.assessment = assessment
        self.calls = []

    async def __call__(self, messages, schema):
        self.calls.append((messages, schema))
        if schema is SearchQueries:
            return SearchQueries(queries=["2025 MT 장소 교통비"])
        assert schema is EvidenceAssessment
        assert self.assessment is not None, "빈 검색 결과에는 근거 판단을 호출하지 않는다"
        return self.assessment


def chunk(record_id, text):
    return RetrievedChunk(
        text=text, source=RecordSource(record_id=record_id, file_name=f"{record_id}.pdf",
                                      location=SourceLocation(label="2쪽 · 장소")),
        category=RecordCategory.EVENT_HISTORY, event_id="event-2025", score=0.9,
    )


def test_mapping_only_copies_search_context_and_keeps_original():
    request = make_request(conditions={
        "title": "올해 행사", "event_type": "MT", "headcount": 40,
        "start_date": "2026-11-01", "end_date": "2026-11-02",
        "location": "올해 장소", "fee_per_person": 50000, "budget_total": 2000000,
    })
    before = request.model_dump()
    mapped = build_record_search_request(request)
    assert mapped.conditions.model_dump(exclude_none=True) == {
        "event_type": "MT", "start_date": date(2026, 11, 1),
    }
    assert mapped.event_id is None
    assert mapped.query == request.query
    assert mapped.today == date(2026, 10, 23)
    assert mapped.limit == 5 and mapped.category is None
    assert request.model_dump() == before


@pytest.mark.parametrize("conditions", [{}, {"headcount": 40}, {"location": "가평"}])
def test_no_search_context_is_none(conditions):
    assert build_record_search_request(make_request(conditions=conditions)).conditions is None


def test_start_date_without_type_is_preserved():
    mapped = build_record_search_request(make_request(conditions={"start_date": "2027-03-20"}))
    assert mapped.conditions.model_dump(exclude_none=True) == {"start_date": date(2027, 3, 20)}


@pytest.mark.parametrize("changes", [
    {"club_id": " "}, {"planning_event_id": ""}, {"request_id": "\n"},
    {"target_event_id": " "}, {"query": " "}, {"query": "가" * 4001},
    {"base_version": True}, {"base_version": -1}, {"base_version": "3"},
    {"reference_date": datetime(2026, 10, 23)}, {"reference_date": 1792710000},
    {"reference_date": "2026-02-30"}, {"reference_date": "2026-1-1"},
    {"unexpected": True},
])
def test_invalid_input_is_rejected(changes):
    with pytest.raises(ValidationError):
        make_request(**changes)


@pytest.mark.parametrize("target", [None, "event-2025", "event-2026"])
def test_actual_retrieval_passes_scope_and_preserves_partial_and_conflicting_evidence(target):
    request = make_request(target_event_id=target)
    before = request.model_dump()
    chunks = (chunk("report", "장소는 가평"), chunk("memo", "장소는 춘천"))
    port = Port(chunks)
    model = Model(EvidenceAssessment.model_validate({
        "sufficient": False, "retry_queries": ["다시 검색"],
        "facts": [{"content": "MT를 진행했다", "chunk_ids": ["c1"]}],
        "not_found": ["2025년 교통비"],
        "conflicts": [{"description": "장소가 다름", "values": [
            {"content": "가평", "chunk_ids": ["c1"]},
            {"content": "춘천", "chunk_ids": ["c2"]},
        ]}],
    }))
    result = asyncio.run(search_planning_records(request, port=port, embed=embed, invoke=model))
    assert len(port.calls) == 1  # 근거가 부족해도 planning에서 추가 검색하지 않는다.
    assert port.calls[0].club_id == "club-1"
    assert port.calls[0].event_id == target
    assert port.calls[0].category is None and port.calls[0].limit == 5
    assert result.status == "AVAILABLE"
    assert (result.planning_event_id, result.request_id, result.base_version) == ("event-2026", "turn-7", 3)
    assert result.cards[0].sources == (chunks[0].source,)
    assert result.not_found == ("2025년 교통비",)
    assert [fact.content for fact in result.conflicts[0].values] == ["가평", "춘천"]
    assert result.conflicts[0].values[1].sources == (chunks[1].source,)
    assert [schema for _, schema in model.calls] == [SearchQueries, EvidenceAssessment]
    assert request.model_dump() == before


def test_empty_search_is_not_an_error_and_keeps_conditions():
    request = make_request()
    before = request.model_dump()
    model = Model()
    result = asyncio.run(search_planning_records(request, port=Port(), embed=embed, invoke=model))
    assert result.status == "NOT_FOUND"
    assert result.cards == result.conflicts == ()
    assert result.not_found == (request.query,)
    assert len(model.calls) == 1
    assert request.model_dump() == before


@pytest.mark.parametrize("failure_at", ["rewrite", "embed", "port", "assessment"])
def test_failures_propagate_without_mutating_conditions(failure_at):
    request = make_request()
    before = request.model_dump()
    failure = PermissionError("denied") if failure_at == "port" else AITimeoutError("timeout")
    port = Port((chunk("report", "장소"),), error=failure if failure_at == "port" else None)

    async def failing_embed(texts):
        if failure_at == "embed":
            raise failure
        return await embed(texts)

    async def failing_model(messages, schema):
        if failure_at == "rewrite" or schema is EvidenceAssessment:
            raise failure
        return SearchQueries(queries=["2025 MT"])

    with pytest.raises(type(failure)) as caught:
        asyncio.run(search_planning_records(request, port=port, embed=failing_embed, invoke=failing_model))
    assert caught.value is failure
    assert request.model_dump() == before


def test_unretrieved_source_is_not_returned_as_success():
    request = make_request()
    before = request.model_dump()
    model = Model(EvidenceAssessment.model_validate({
        "sufficient": True, "retry_queries": [], "not_found": [], "conflicts": [],
        "facts": [{"content": "근거 없는 장소", "chunk_ids": ["c99"]}],
    }))
    with pytest.raises(AIInvalidResponseError):
        asyncio.run(search_planning_records(
            request, port=Port((chunk("report", "가평"),)), embed=embed, invoke=model,
        ))
    assert request.model_dump() == before
