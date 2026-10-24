"""새 Agent 1단계: 값·잠정 정보·보류를 함께 갱신하고 실패 시 원본을 보존한다."""

import pytest
from pydantic import ValidationError

from app.ai.features.planning.agent.state import ConditionMeta, PlanningDraft
from app.ai.features.planning.agent.tools import UpdateEventConditionsInput, update_event_conditions
from app.ai.features.planning.schemas import MessageEvidence, PlanningConditions, PlanningMessage


MESSAGE = PlanningMessage(id="user-1", role="user", text="날짜는 나중에, 대략 50명에 인당 25,000원으로 잡자")
EVIDENCE = {"message_id": MESSAGE.id, "quote": MESSAGE.text}


def set_value(field, value, status="tentative", evidence=None):
    return {"op": "SET", "change": {"field": field, "value": value},
            "status": status, "evidence": evidence or EVIDENCE}


def run(draft=None, *, changes=(), defer_topics=(), resume_topics=(), message=MESSAGE):
    request = UpdateEventConditionsInput(changes=changes, defer_topics=defer_topics, resume_topics=resume_topics)
    return update_event_conditions(draft or PlanningDraft(), request, current_message=message)


def test_multiple_tentative_values_and_deferred_dates_preserve_other_values_and_input():
    original = PlanningDraft(conditions=PlanningConditions(event_type="MT", location="대구"))
    before = original.model_dump_json()
    result = run(original, changes=[
        set_value("headcount", 50, evidence={"message_id": MESSAGE.id, "quote": "대략 50명"}),
        set_value("fee_per_person", 25000, evidence={"message_id": MESSAGE.id, "quote": "인당 25,000원"}),
    ], defer_topics=[{"topic": "dates", "evidence": {"message_id": MESSAGE.id, "quote": "날짜는 나중에"}}])
    assert result.status == "applied"
    assert result.changed_fields == ("headcount", "fee_per_person")
    assert result.draft.conditions.headcount == 50
    assert result.draft.conditions.fee_per_person == 25000
    assert result.draft.conditions.location == "대구"
    assert result.draft.conditions.event_type == "MT"
    assert result.draft.conditions.start_date is None
    assert result.draft.condition_meta["headcount"].status == "tentative"
    assert result.draft.deferred_topics == ("dates",)
    assert original.model_dump_json() == before
    assert original.condition_meta == {}


def test_clear_is_unknown_not_free_and_removes_metadata():
    free = run(changes=[set_value("fee_per_person", 0)]).draft
    result = run(free, changes=[{"op": "CLEAR", "field": "fee_per_person", "evidence": EVIDENCE}])
    assert free.conditions.fee_per_person == 0
    assert result.draft.conditions.fee_per_person is None
    assert "fee_per_person" not in result.draft.condition_meta
    assert "fee_per_person" in free.condition_meta


def test_same_value_can_change_from_tentative_to_specified():
    original = run(changes=[set_value("headcount", 50)]).draft
    result = run(original, changes=[set_value("headcount", 50, status="specified")])
    assert result.status == "applied"
    assert result.changed_fields == ("headcount",)
    assert result.draft.condition_meta["headcount"].status == "specified"
    assert original.condition_meta["headcount"].status == "tentative"


def test_reapplying_identical_request_is_unchanged():
    first = run(changes=[set_value("headcount", 50)])
    second = run(first.draft, changes=[set_value("headcount", 50)])
    assert second.status == "unchanged"
    assert second.changed_fields == ()
    assert second.draft is first.draft


def test_defer_and_resume_without_changing_values():
    original = PlanningDraft(conditions=PlanningConditions(headcount=32))
    deferred = run(original, defer_topics=[{"topic": "dates", "evidence": EVIDENCE}])
    assert deferred.status == "applied"
    assert deferred.changed_fields == ()
    assert deferred.draft.conditions == original.conditions
    resumed = run(deferred.draft, resume_topics=[{"topic": "dates", "evidence": EVIDENCE}])
    assert resumed.draft.deferred_topics == ()
    assert resumed.draft.conditions == original.conditions


def test_setting_one_date_resumes_dates_but_preserves_other_deferrals():
    original = PlanningDraft(deferred_topics=("headcount", "dates"))
    result = run(original, changes=[set_value("start_date", "2027-03-20")])
    assert result.draft.deferred_topics == ("headcount",)
    assert original.deferred_topics == ("headcount", "dates")


def test_clear_does_not_resume_deferred_topic():
    original = PlanningDraft(conditions=PlanningConditions(headcount=32), deferred_topics=("headcount",))
    result = run(original, changes=[{"op": "CLEAR", "field": "headcount", "evidence": EVIDENCE}])
    assert result.draft.deferred_topics == ("headcount",)


def test_dates_are_validated_as_a_final_pair_not_intermediate_steps():
    original = PlanningDraft(conditions=PlanningConditions(start_date="2027-03-20", end_date="2027-03-21"))
    result = run(original, changes=[set_value("start_date", "2027-04-20"), set_value("end_date", "2027-04-21")])
    assert result.status == "applied"
    assert result.draft.conditions.start_date.isoformat() == "2027-04-20"


def test_conflicting_date_rejects_entire_bundle_including_valid_headcount_and_deferral():
    original = PlanningDraft(conditions=PlanningConditions(start_date="2027-03-20", end_date="2027-03-21", headcount=32))
    result = run(original, changes=[set_value("start_date", "2027-04-20"), set_value("headcount", 50)],
                 defer_topics=[{"topic": "location", "evidence": EVIDENCE}])
    assert result.status == "rejected"
    assert result.draft is original
    assert result.changed_fields == ()
    assert "종료일" in result.reason
    assert original.condition_meta == {}


@pytest.mark.parametrize("evidence", [
    {"message_id": "another-user", "quote": MESSAGE.text},
    {"message_id": MESSAGE.id, "quote": "발화에 없는 말"},
])
def test_invalid_evidence_rejects_bundle(evidence):
    original = PlanningDraft()
    result = run(original, changes=[set_value("headcount", 50, evidence=evidence)])
    assert result.status == "rejected"
    assert result.draft is original
    assert "근거" in result.reason


def test_deferral_also_requires_current_evidence():
    result = run(defer_topics=[{"topic": "dates", "evidence": {"message_id": "old", "quote": MESSAGE.text}}])
    assert result.status == "rejected"


def test_assistant_message_cannot_authorize_change():
    result = run(changes=[set_value("headcount", 50)], message=MESSAGE.model_copy(update={"role": "assistant"}))
    assert result.status == "rejected"


@pytest.mark.parametrize("changes,defer,resume", [
    ([set_value("headcount", 50), set_value("headcount", 40)], [], []),
    ([], ["dates", "dates"], []),
    ([], [], ["dates", "dates"]),
    ([], ["dates"], ["dates"]),
    ([set_value("start_date", "2027-03-20")], ["dates"], []),
])
def test_ambiguous_duplicate_or_opposing_operations_are_rejected(changes, defer, resume):
    result = run(changes=changes,
                 defer_topics=[{"topic": topic, "evidence": EVIDENCE} for topic in defer],
                 resume_topics=[{"topic": topic, "evidence": EVIDENCE} for topic in resume])
    assert result.status == "rejected"
    assert result.draft == PlanningDraft()


@pytest.mark.parametrize("field,value", [("headcount", 0), ("headcount", "50"),
                                          ("headcount", True), ("fee_per_person", -1),
                                          ("location", " "), ("event_type", "UNKNOWN")])
def test_invalid_field_values_fail_input_validation(field, value):
    with pytest.raises(ValidationError):
        UpdateEventConditionsInput(changes=[set_value(field, value)])


def test_noop_does_not_normalize_order_or_mutate_input():
    original = PlanningDraft(deferred_topics=("location", "dates"))
    result = run(original)
    assert result.status == "unchanged"
    assert result.draft is original


def test_metadata_without_value_and_duplicate_topics_are_invalid():
    with pytest.raises(ValidationError):
        PlanningDraft(condition_meta={"headcount": ConditionMeta(status="tentative", evidence=MessageEvidence(**EVIDENCE))})
    with pytest.raises(ValidationError):
        PlanningDraft(deferred_topics=("dates", "dates"))


def test_draft_and_tool_input_round_trip_through_json():
    result = run(changes=[set_value("headcount", 50)])
    assert PlanningDraft.model_validate_json(result.draft.model_dump_json()) == result.draft
    request = UpdateEventConditionsInput(changes=[set_value("headcount", 50)])
    assert UpdateEventConditionsInput.model_validate_json(request.model_dump_json()) == request
