"""실제 추출·검증·검색 함수를 통과하고 외부 모델과 port만 대체한다."""

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.ai.errors import AIConfigError, AIInvalidResponseError, AIRetryableError, AITimeoutError
from app.ai.features.planning.lookup import RecordLookupDecision
from app.ai.features.planning.schemas import ConditionExtractionOutput
from app.ai.features.planning.turn_flow import prepare_planning_turn
from app.ai.features.planning.turn_schemas import PlanningTurnInput
from app.ai.features.retrieval.schemas import SearchQueries
from app.ai.llm import EMBEDDING_DIMENSIONS


def request(text="40명으로 하고 작년 장소도 알려줘", **changes):
    source = dict(event_id="e1", request_id="r1", base_version=0,
                  conditions={"event_type": "MT", "headcount": 60},
                  current_message={"id": "m1", "role": "user", "text": text},
                  reference_date="2026-10-23", timezone="Asia/Seoul")
    source.update(changes)
    return PlanningTurnInput.model_validate({"club_id": "c1", "extraction_input": source,
                                            "question_state": {"event_id": "e1"}})


def decision(action, quote, **changes):
    values = dict(action=action, query="작년 MT 장소" if action == "SEARCH" else None,
                  clarification="어떤 행사를 말하나요?" if action == "CLARIFY" else None,
                  evidence={"message_id": "m1", "quote": quote})
    values.update(changes)
    return RecordLookupDecision.model_validate(values)


class Port:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def search_chunks(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return ()


async def embed(texts):
    return [(1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1) for _ in texts]


async def invoke(messages, schema):
    assert schema is SearchQueries
    return SearchQueries(queries=["2025 MT 장소"])


def run(req, action="SEARCH", operations=(), port=None, **overrides):
    async def extract(messages):
        return ConditionExtractionOutput.model_validate({"operations": operations, "unresolved": []})

    async def decide(messages):
        payload = json.loads(messages[-1].content)
        assert "club_id" not in payload and "event_id" not in payload
        return decision(action, req.extraction_input.current_message.text)

    options = dict(extract=extract, decide=decide, embed=embed, invoke=invoke)
    options.update(overrides)
    return asyncio.run(prepare_planning_turn(req, port=port or Port(), **options))


def set_people():
    return {"op": "SET", "change": {"field": "headcount", "value": 40},
            "evidence": {"message_id": "m1", "quote": "40명으로"},
            "offer_id": None, "context_evidence": []}


@pytest.mark.parametrize("text,action,ops,status", [
    ("40명으로", "SKIP", [set_people()], "SKIPPED"),
    ("작년 MT 장소는?", "SEARCH", [], "SUCCEEDED"),
    ("40명으로 하고 작년 장소도 알려줘", "SEARCH", [set_people()], "SUCCEEDED"),
    ("그때 그 행사 비용은?", "CLARIFY", [], "NEEDS_CLARIFICATION"),
    ("작년엔 28명이었고 올해는 40명으로", "SKIP", [set_people()], "SKIPPED"),
    ("아직 모르겠어", "SKIP", [], "SKIPPED"),
])
def test_execution_branch(text, action, ops, status):
    req = request(text); before = req.model_dump(); port = Port()
    result = run(req, action, ops, port)
    assert result.record_lookup.status == status
    assert len(port.calls) == (1 if action == "SEARCH" else 0)
    assert result.extraction.candidate_conditions.headcount == (40 if ops else 60)
    if port.calls:
        assert port.calls[0].club_id == "c1" and port.calls[0].event_id is None
        assert result.record_lookup.result.status == "NOT_FOUND"
    assert req.model_dump() == before


@pytest.mark.parametrize("error,code", [(AITimeoutError(), "TIMEOUT"),
    (AIInvalidResponseError(), "INVALID_RESPONSE"), (AIRetryableError(), "RETRYABLE")])
def test_only_search_retryable_failures_preserve_changes(error, code):
    result = run(request(), operations=[set_people()], port=Port(error))
    assert result.record_lookup.error_code == code
    assert result.extraction.candidate_conditions.headcount == 40


@pytest.mark.parametrize("error", [PermissionError(), AIConfigError(), RuntimeError()])
def test_non_retryable_search_failures_propagate(error):
    with pytest.raises(type(error)):
        run(request(), port=Port(error))


@pytest.mark.parametrize("phase", ["extract", "decide"])
def test_upstream_failure_does_not_become_partial_success(phase):
    async def fail(_):
        raise AITimeoutError()
    port = Port()
    with pytest.raises(AITimeoutError):
        run(request(), port=port, **{phase: fail})
    assert not port.calls


def test_wrong_lookup_evidence_is_rejected_before_search():
    async def wrong(_):
        return decision("SEARCH", "없는 근거")
    port = Port()
    with pytest.raises(AIInvalidResponseError):
        run(request(), decide=wrong, port=port)
    assert not port.calls


def test_lookup_payload_cannot_mix_actions():
    with pytest.raises(ValidationError):
        decision("SKIP", "hello", query="검색")


def test_date_conflict_keeps_original_and_still_allows_independent_lookup():
    req = request("시작일은 2027-03-22로 바꾸고 작년 장소도 알려줘", conditions={
        "event_type": "MT", "start_date": "2027-03-20", "end_date": "2027-03-21"})
    op = {**set_people(), "change": {"field": "start_date", "value": "2027-03-22"},
          "evidence": {"message_id": "m1", "quote": "시작일은 2027-03-22로"}}
    result = run(req, operations=[op])
    assert result.extraction.status == "VALIDATION_FAILED"
    assert result.extraction.candidate_conditions == req.extraction_input.conditions
    assert result.record_lookup.status == "SUCCEEDED"
