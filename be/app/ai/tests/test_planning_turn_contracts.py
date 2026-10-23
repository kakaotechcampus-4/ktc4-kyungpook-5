"""한 턴 내부 계약의 혼입·모순과 생성 정책 경계를 검증한다."""

import pytest
from pydantic import ValidationError

from app.ai.features.planning.schemas import PlanningConditions
from app.ai.features.planning.turn_policy import assess_generation_readiness
from app.ai.features.planning.turn_schemas import PlanningTurnInput, PlanningTurnResult, RecordLookupState


def extraction():
    return dict(event_id="e1", request_id="r1", base_version=0,
                status="UNCHANGED", candidate_conditions={"event_type": "MT"},
                applied_operations=[], unresolved=[], validation_errors=[],
                prompt_version="test", extraction_ms=0)


def output(**overrides):
    return dict(event_id="e1", request_id="r1", base_version=0, extraction=extraction(),
                collected={"event_type": "MT"}, reply="MT 초안을 만들 수 있어요.",
                next_question_state={"event_id": "e1"}, record_lookup={"status": "SKIPPED"},
                readiness={"ready_to_generate": True, "reasons": []}, **overrides)


def pending(field="headcount", id="pending-1"):
    return dict(id=id, item=dict(field=field, reason="AMBIGUOUS_VALUE",
                evidence={"message_id": "old-message", "quote": "좀 줄이자"}))


@pytest.mark.parametrize("conditions,kwargs,reasons", [
    ({}, {}, ("MISSING_EVENT_TYPE",)),
    ({"title": "우리 행사"}, {}, ("MISSING_EVENT_TYPE",)),
    ({"event_type": "MT"}, {}, ()),
    ({"event_type": "ETC"}, {}, ()),
    ({"event_type": "MT"}, {"has_pending_modification": True}, ("PENDING_MODIFICATION",)),
    ({"event_type": "MT"}, {"has_condition_conflict": True}, ("CONDITION_CONFLICT",)),
])
def test_readiness_distinguishes_unknown_from_pending(conditions, kwargs, reasons):
    result = assess_generation_readiness(PlanningConditions(**conditions), **kwargs)
    assert result.reasons == reasons
    assert result.ready_to_generate == (not reasons)


def test_search_failure_does_not_block_valid_conditions():
    data = output()
    data["record_lookup"] = {"status": "FAILED", "error_code": "TIMEOUT"}
    result = PlanningTurnResult.model_validate(data)
    assert result.readiness.ready_to_generate
    assert PlanningTurnResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("payload", [
    {"status": "SUCCEEDED"}, {"status": "FAILED"},
    {"status": "SKIPPED", "error_code": "TIMEOUT"},
    {"status": "NEEDS_CLARIFICATION"},
    {"status": "FAILED", "error_code": "raw-secret-error"},
])
def test_lookup_rejects_inconsistent_payloads(payload):
    with pytest.raises(ValidationError):
        RecordLookupState.model_validate(payload)


@pytest.mark.parametrize("change", [
    {"request_id": "r2"}, {"event_id": "e2"}, {"base_version": 2},
    {"collected": {"event_type": "MT", "headcount": 10}},
    {"next_question_state": {"event_id": "e2"}},
    {"pending_clarifications": [pending()]},
    {"readiness": {"ready_to_generate": False, "reasons": []}},
])
def test_turn_rejects_mixed_or_contradictory_results(change):
    data = output(); data.update(change)
    with pytest.raises(ValidationError):
        PlanningTurnResult.model_validate(data)


def test_lookup_identity_is_checked():
    data = output()
    data["record_lookup"] = {"status": "SUCCEEDED", "result": {
        "planning_event_id": "e2", "request_id": "r1", "base_version": 0,
        "status": "NOT_FOUND", "not_found": ["작년 장소"],
    }}
    with pytest.raises(ValidationError):
        PlanningTurnResult.model_validate(data)


def test_question_must_match_display_and_history():
    data = output()
    data["question"] = {"fields": ["location"], "reason": "MISSING", "text": "장소는요?"}
    with pytest.raises(ValidationError):
        PlanningTurnResult.model_validate(data)
    data["reply"] += " 장소는요?"
    data["next_question_state"].update(asked_fields=["location"], last_question_fields=["location"])
    assert PlanningTurnResult.model_validate(data).question.text == "장소는요?"


@pytest.mark.parametrize("items", [
    [pending(), pending(id="another")], [pending(), pending(field="location")],
    [dict(id="p", item=dict(field=None, reason="DEFERRED", evidence={"message_id": "m", "quote": "나중에"}))],
])
def test_input_rejects_duplicate_or_deferred_pending(items):
    data = {"club_id": "c1", "question_state": {"event_id": "e1"},
            "extraction_input": {"event_id": "e1", "request_id": "r1", "base_version": 0,
                "conditions": {}, "current_message": {"id": "m1", "role": "user", "text": "MT"},
                "reference_date": "2026-10-23", "timezone": "Asia/Seoul"},
            "pending_clarifications": items}
    with pytest.raises(ValidationError):
        PlanningTurnInput.model_validate(data)


def test_deferred_extraction_is_not_an_active_modification():
    data = output()
    data["extraction"]["unresolved"] = [{"field": "location", "reason": "DEFERRED",
                                          "evidence": {"message_id": "m1", "quote": "나중에"}}]
    assert PlanningTurnResult.model_validate(data).readiness.ready_to_generate


def test_active_modification_is_preserved_and_blocks_generation():
    data = output()
    item = pending()
    data["extraction"]["unresolved"] = [item["item"]]
    data["readiness"] = {"ready_to_generate": False, "reasons": ["PENDING_MODIFICATION"]}
    with pytest.raises(ValidationError):
        PlanningTurnResult.model_validate(data)
    data["pending_clarifications"] = [item]
    assert not PlanningTurnResult.model_validate(data).readiness.ready_to_generate
