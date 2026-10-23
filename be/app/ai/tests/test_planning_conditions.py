"""P1 조건 경계: 미정·무료, 묵시적 형변환, 날짜 관계와 참고값 분리."""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.ai.features.planning.schemas import PlanningConditions
from app.core.enums import EventType


def test_unresolved_conditions_do_not_invent_defaults():
    assert all(value is None for value in PlanningConditions().model_dump().values())
    assert PlanningConditions(fee_per_person=0).fee_per_person == 0
    assert PlanningConditions(event_type=EventType.ETC).event_type is EventType.ETC


def test_snapshot_round_trip_preserves_confirmed_values():
    original = PlanningConditions(
        title="봄 MT", event_type=EventType.MT, headcount=32,
        fee_per_person=45000, budget_total=2000000,
        start_date=date(2027, 3, 20), end_date="2027-03-21", location="가평",
    )
    assert PlanningConditions.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize("field", ["headcount", "fee_per_person", "budget_total"])
@pytest.mark.parametrize("value", [True, False, "32", 32.0, 3.5, -1])
def test_numeric_values_are_not_silently_coerced(field, value):
    with pytest.raises(ValidationError):
        PlanningConditions(**{field: value})


def test_zero_people_is_invalid_but_zero_budget_is_valid():
    with pytest.raises(ValidationError):
        PlanningConditions(headcount=0)
    assert PlanningConditions(budget_total=0).budget_total == 0


@pytest.mark.parametrize("field,limit", [("title", 100), ("location", 200)])
def test_text_limits_and_blank_values(field, limit):
    assert getattr(PlanningConditions(**{field: "가" * limit}), field) == "가" * limit
    for value in ["", " \n\t", "가" * (limit + 1), 123]:
        with pytest.raises(ValidationError):
            PlanningConditions(**{field: value})


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize("value", [
    "2027-02-29", "2027-3-1", "20270301", "다음 달", "2027-03-01T00:00:00",
    datetime(2027, 3, 1), 0, True,
])
def test_dates_cannot_be_guessed_or_truncated(field, value):
    with pytest.raises(ValidationError):
        PlanningConditions(**{field: value})


def test_date_relation_allows_partial_and_same_day_events():
    assert PlanningConditions(start_date="2027-03-20").end_date is None
    assert PlanningConditions(end_date="2027-03-21").start_date is None
    PlanningConditions(start_date="2027-03-20", end_date="2027-03-20")
    with pytest.raises(ValidationError):
        PlanningConditions(start_date="2027-03-21", end_date="2027-03-20")


def test_reference_candidates_are_not_snapshot_fields():
    with pytest.raises(ValidationError):
        PlanningConditions(location_candidates=["가평", "춘천"])
    with pytest.raises(ValidationError):
        PlanningConditions(event_type="UNKNOWN")


def test_snapshot_is_immutable():
    original = PlanningConditions(headcount=32)
    with pytest.raises(ValidationError):
        original.headcount = 40
    assert original.headcount == 32
