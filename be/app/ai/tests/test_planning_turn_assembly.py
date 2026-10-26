"""답변·질문 상태·미해결 수정이 여러 턴에서 일치하는지 확인한다."""

import asyncio

import pytest

from app.ai.errors import AITimeoutError
from app.ai.features.planning.legacy.lookup import RecordLookupDecision
from app.ai.features.planning.legacy.schemas import ConditionExtractionOutput
from app.ai.features.planning.legacy.turn_assembly import assemble_planning_turn
from app.ai.features.planning.legacy.turn_flow import process_planning_turn
from app.ai.features.planning.legacy.turn_schemas import PendingClarification, PlanningTurnInput, RecordLookupState
from test_planning_turn_flow import Port, request, run, set_people


def pending(field="headcount"):
    return PendingClarification.model_validate({"id": "old:" + str(field), "item": {
        "field": field, "reason": "AMBIGUOUS_VALUE",
        "evidence": {"message_id": "old", "quote": "좀 줄이자"}}})


def with_pending(req, *fields):
    return PlanningTurnInput.model_validate({**req.model_dump(),
                                            "pending_clarifications": [pending(f) for f in fields]})


def test_mixed_search_failure_explains_change_without_unrelated_question():
    req = request(); before = req.model_dump()
    result = assemble_planning_turn(req, run(req, operations=[set_people()], port=Port(AITimeoutError())))
    assert "40명" in result.reply and "검색에 실패" in result.reply
    assert result.collected.headcount == 40 and result.collected.location is None
    assert result.question is None
    assert result.next_question_state.asked_fields == ()
    assert result.readiness.ready_to_generate
    assert req.model_dump() == before


def test_lookup_clarification_does_not_consume_hidden_condition_question():
    req = with_pending(request("그때 그 행사 비용은?"), "headcount")
    result = assemble_planning_turn(req, run(req, action="CLARIFY"))
    assert result.question.text == "어떤 행사를 말하나요?"
    assert result.next_question_state.asked_fields == ()
    assert result.pending_clarifications == req.pending_clarifications
    assert not result.readiness.ready_to_generate


@pytest.mark.parametrize("count", [60, 40])
def test_explicit_answer_resolves_pending_even_when_value_is_unchanged(count):
    req = with_pending(request("40명으로", conditions={"event_type": "MT", "headcount": count}), "headcount")
    result = assemble_planning_turn(req, run(req, action="SKIP", operations=[set_people()]))
    assert result.pending_clarifications == ()
    assert result.question.fields == ("start_date", "end_date")
    assert result.readiness.ready_to_generate


def test_unrelated_answer_keeps_other_pending_and_unknown_target():
    req = with_pending(request("40명으로"), "headcount", "location", None)
    result = assemble_planning_turn(req, run(req, action="SKIP", operations=[set_people()]))
    assert [p.item.field for p in result.pending_clarifications] == ["location", None]
    assert result.question.fields == ("location",)
    assert not result.readiness.ready_to_generate


def test_explicit_defer_clears_pending_without_clearing_existing_value():
    req = with_pending(request("인원은 나중에 정할게"), "headcount")
    async def extract(_):
        return ConditionExtractionOutput.model_validate({"operations": [], "unresolved": [{
            "field": "headcount", "reason": "DEFERRED",
            "evidence": {"message_id": "m1", "quote": "인원은 나중에 정할게"}}]})
    result = assemble_planning_turn(req, run(req, action="SKIP", extract=extract))
    assert result.pending_clarifications == ()
    assert "headcount" in result.next_question_state.deferred_fields
    assert result.collected.headcount == 60


def test_conflict_remains_pending_across_readonly_turn():
    req = request("시작일은 2027-03-22로", conditions={
        "event_type": "MT", "start_date": "2027-03-20", "end_date": "2027-03-21"})
    op = {**set_people(), "change": {"field": "start_date", "value": "2027-03-22"},
          "evidence": {"message_id": "m1", "quote": req.extraction_input.current_message.text}}
    first = assemble_planning_turn(req, run(req, action="SKIP", operations=[op]))
    assert first.question.reason == "CONFLICT" and not first.readiness.ready_to_generate
    next_req = request("작년 장소는?", conditions=first.collected.model_dump())
    next_req = PlanningTurnInput.model_validate({**next_req.model_dump(),
        "pending_clarifications": first.pending_clarifications,
        "question_state": first.next_question_state})
    second = assemble_planning_turn(next_req, run(next_req))
    assert second.pending_clarifications and not second.readiness.ready_to_generate


def test_different_request_preparation_is_rejected():
    req = request(); prepared = run(req)
    changed = req.model_copy(update={"extraction_input": req.extraction_input.model_copy(update={"request_id": "another"})})
    with pytest.raises(ValueError):
        assemble_planning_turn(changed, prepared)


def test_internal_end_to_end_turn_returns_display_and_state():
    req = request("40명으로")
    async def extract(_):
        return ConditionExtractionOutput.model_validate({"operations": [set_people()], "unresolved": []})
    async def decide(_):
        return RecordLookupDecision.model_validate({"action": "SKIP", "query": None, "clarification": None,
            "evidence": {"message_id": "m1", "quote": "40명으로"}})
    port = Port()
    result = asyncio.run(process_planning_turn(req, port=port, extract=extract, decide=decide))
    assert "40명" in result.reply and result.reply.count(result.question.text) == 1
    assert result.next_question_state.last_question_fields == result.question.fields
    assert not port.calls


def test_cards_conflicts_and_missing_evidence_are_all_explained():
    req = request("작년 장소는?"); prepared = run(req)
    def fact(content, record):
        return {"content": content, "sources": [{"record_id": record, "file_name": record + ".pdf",
                                                  "location": {"label": "2쪽"}}]}
    lookup = RecordLookupState.model_validate({"status": "SUCCEEDED", "result": {
        "planning_event_id": "e1", "request_id": "r1", "base_version": 0, "status": "AVAILABLE",
        "cards": [fact("가평 기록", "r1")], "not_found": ["교통비"],
        "conflicts": [{"description": "장소 차이", "values": [fact("가평", "r1"), fact("춘천", "r2")]}],
    }})
    result = assemble_planning_turn(req, prepared.model_copy(update={"record_lookup": lookup}))
    for fragment in ["가평 기록", "r1.pdf", "2쪽", "장소 차이", "춘천", "r2.pdf", "교통비"]:
        assert fragment in result.reply
    assert result.question is None and result.collected.location is None
