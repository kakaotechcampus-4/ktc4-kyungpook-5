"""질문 우선순위·미루기·반복 방지와 행사 격리를 검증한다."""

import pytest

from app.ai.features.planning.legacy.questions import PlanningQuestionState, select_next_question
from app.ai.features.planning.legacy.schemas import ConditionExtractionResult


def result(conditions=None, unresolved=(), **overrides):
    return ConditionExtractionResult.model_validate({
        "event_id": "e1", "request_id": "r1", "base_version": 0,
        "candidate_conditions": conditions or {}, "status": "UNCHANGED",
        "applied_operations": [], "unresolved": unresolved, "validation_errors": [],
        "prompt_version": "test", "extraction_ms": 0, **overrides,
    })


def unresolved(field, reason="AMBIGUOUS_VALUE"):
    return {"field": field, "reason": reason, "evidence": {"message_id": "m1", "quote": "미정"}}


def test_current_ambiguity_takes_priority_over_other_missing_fields():
    original = result({"headcount": 32}, [unresolved("headcount")])
    answer = select_next_question(original, PlanningQuestionState(event_id="e1"))
    assert answer.question.fields == ("headcount",)
    assert answer.question.text == "예상 인원을 몇 명으로 바꿀까요?"
    assert original.candidate_conditions.headcount == 32
    assert answer.question.allow_free_text
    assert len(answer.question.quick_replies) <= 4


def test_only_one_topic_is_selected():
    answer = select_next_question(result(unresolved=[unresolved("headcount"), unresolved("location")]), PlanningQuestionState(event_id="e1"))
    assert answer.question.fields == ("headcount",)


@pytest.mark.parametrize("field", [None, "headcount"])
def test_deferred_answer_skips_previous_topic(field):
    state = PlanningQuestionState(event_id="e1", asked_fields=("headcount",), last_question_fields=("headcount",))
    answer = select_next_question(result(unresolved=[unresolved(field, "DEFERRED")]), state)
    assert "headcount" in answer.state.deferred_fields
    assert answer.question.fields == ("event_type",)
    assert state.deferred_fields == ()


def test_no_answer_does_not_repeat_previous_missing_topic():
    first = select_next_question(result(), PlanningQuestionState(event_id="e1"))
    assert first.question.fields == ("event_type",)
    second = select_next_question(result(), first.state)
    assert second.question.fields == ("start_date", "end_date")


def test_known_values_are_skipped_and_budget_is_not_required():
    answer = select_next_question(result({
        "event_type": "MT", "title": "봄 MT", "headcount": 32, "location": "가평",
        "fee_per_person": 0, "start_date": "2027-03-20", "end_date": "2027-03-21",
    }), PlanningQuestionState(event_id="e1"))
    assert answer.question is None


def test_user_can_reopen_deferred_field_explicitly():
    answer = select_next_question(result(unresolved=[unresolved("location")]),
        PlanningQuestionState(event_id="e1", deferred_fields=("location",), asked_fields=("location",)))
    assert answer.question.fields == ("location",)
    assert "location" not in answer.state.deferred_fields


def test_clear_reopens_a_previously_asked_missing_field():
    fields = ("event_type", "start_date", "end_date", "headcount", "location", "title", "fee_per_person")
    extraction = result(applied_operations=[{
        "op": "CLEAR", "field": "location", "evidence": {"message_id": "m1", "quote": "다시"},
    }])
    answer = select_next_question(extraction, PlanningQuestionState(event_id="e1", asked_fields=fields, deferred_fields=("location",)))
    assert answer.question.fields == ("location",)
    assert "location" not in answer.state.deferred_fields


def test_dates_are_one_topic_and_conflict_does_not_claim_success():
    state = PlanningQuestionState(event_id="e1", last_question_fields=("start_date", "end_date"))
    answer = select_next_question(result(unresolved=[unresolved("start_date", "DEFERRED")]), state)
    assert set(answer.state.deferred_fields) == {"start_date", "end_date"}
    conflict = select_next_question(result(status="VALIDATION_FAILED", validation_errors=["END_BEFORE_START"]), state)
    assert conflict.question.reason == "CONFLICT"
    assert "반영하지 않았어요" in conflict.question.text


def test_unknown_target_gets_generic_clarification():
    answer = select_next_question(result(unresolved=[unresolved(None, "AMBIGUOUS_REFERENCE")]), PlanningQuestionState(event_id="e1"))
    assert answer.question.fields == ()
    assert answer.question.reason == "CLARIFY"


@pytest.mark.parametrize("known,question_text", [
    ({"start_date": "2027-03-20"}, "시작일은 2027-03-20로 정해져 있어요. 종료일은 언제인가요?"),
    ({"end_date": "2027-03-21"}, "종료일은 2027-03-21로 정해져 있어요. 시작일은 언제인가요?"),
])
def test_partial_schedule_only_asks_for_unknown_date(known, question_text):
    answer = select_next_question(result({"event_type": "MT", **known}), PlanningQuestionState(event_id="e1"))
    assert answer.question.text == question_text


def test_event_isolation_and_unknown_validation_errors():
    with pytest.raises(ValueError):
        select_next_question(result(), PlanningQuestionState(event_id="other"))
    with pytest.raises(ValueError):
        select_next_question(result(status="VALIDATION_FAILED", validation_errors=["UNKNOWN"]), PlanningQuestionState(event_id="e1"))
