import pytest
from pydantic import ValidationError

import app.ai as ai
from app.core.enums import EventStatus


def event(**changes):
    values = dict(event_id='evt-1', title='2026 봄 MT', status=EventStatus.ON_GOING,
                  start_date='2026-11-10', end_date='2026-11-12', location='경주',
                  expected_headcount=40, actual_headcount=36)
    return ai.MeetingEventFact(**(values | changes))


def test_actual_and_expected_counts_are_separate():
    result = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='current', fields=('status', 'dates', 'expected_headcount', 'actual_headcount'),
        events=(event(),), complete=True,
    ))
    assert result.status == 'answered'
    assert '예상 인원: 40명' in result.answer
    assert '실제 참가 인원: 36명' in result.answer
    assert result.event_ids == ('evt-1',)


def test_recent_without_verified_full_order_is_partial():
    result = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='recent', fields=('status',), events=(event(),), complete=True,
    ))
    assert result.status == 'partial'
    assert '가장 최근인지 확인하지 못했어요' in result.answer


def test_unknown_actual_count_is_not_replaced_with_expected():
    result = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='selected', fields=('actual_headcount',),
        events=(event(actual_headcount=None),), complete=True,
    ))
    assert result.status == 'partial'
    assert '실제 참가 인원: 미확인' in result.answer
    assert '40' not in result.answer


def test_verified_recent_result_is_answered():
    result = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='recent', fields=('status',), events=(event(),),
        complete=True, latest_verified=True,
    ))
    assert result.status == 'answered'
    assert result.event_ids == ('evt-1',)


def test_incomplete_empty_scope_is_unavailable_and_complete_empty_is_not_found():
    unavailable = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='current', fields=('status',), events=(), complete=False,
    ))
    not_found = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope='current', fields=('status',), events=(), complete=True,
    ))
    assert unavailable.status == 'unavailable'
    assert not_found.status == 'not_found'


def test_latest_verification_requires_complete_recent_query_and_contract_blocks_guesses():
    with pytest.raises(ValidationError):
        ai.MeetingEventFactsRequest(scope='current', fields=('status',), events=(event(),),
                                    complete=True, latest_verified=True)
    with pytest.raises(ValidationError):
        ai.MeetingEventFactsRequest(scope='recent', fields=('status', 'status'), events=(event(),), complete=True)
    with pytest.raises(ValidationError):
        ai.MeetingEventFact(**dict(event_id='evt-1', title='행사', status='ON_GOING',
                                   start_date='2026-11-12', end_date='2026-11-10'))
