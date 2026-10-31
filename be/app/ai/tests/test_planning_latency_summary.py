"""검사용 숫자의 통계를 미리 계산해 실패와 준비 실행의 혼입을 잡는다."""

import math

import pytest

from app.ai.scripts.planning_latency_summary import distribution, summarize_group


def record(outcome, elapsed, category='timeout'):
    return dict(outcome=outcome, ai_request_ms=elapsed, failure=dict(category=category))


def test_linear_percentiles_follow_known_values():
    result = distribution([6, 2, 5, 3, 4])
    assert result == dict(n=5, p50_ms=4, p95_ms=5.8, mean_ms=4, max_ms=6)
    assert distribution([10, 20])['p50_ms'] == 15
    assert distribution([10, 20])['p95_ms'] == 19.5


def test_empty_samples_are_unknown_and_single_sample_is_preserved():
    assert distribution([]) == dict(n=0, p50_ms=None, p95_ms=None, mean_ms=None, max_ms=None)
    assert distribution([7]) == dict(n=1, p50_ms=7, p95_ms=7, mean_ms=7, max_ms=7)
    assert distribution([0])['p50_ms'] == 0


@pytest.mark.parametrize('value', [-1, math.nan, math.inf, True])
def test_invalid_durations_are_not_silently_removed(value):
    with pytest.raises(ValueError):
        distribution([value])


def test_success_denominator_keeps_failures_but_success_latency_does_not():
    finished = [record('success', value) for value in range(1, 29)]
    finished += [record('failed', 100), record('failed', 200, 'invalid_output')]
    result = summarize_group([None] * 30, [None] * 30, finished)
    assert result['success_rate'] == pytest.approx(28 / 30)
    assert result['success_ms']['n'] == 28
    assert result['success_ms']['p50_ms'] == 14.5
    assert result['success_ms']['p95_ms'] == pytest.approx(26.65)
    assert result['failure_ms']['n'] == 2
    assert result['failure_ms']['p50_ms'] == 150
    assert result['completed_ms']['n'] == 30
    assert result['failures_by_category']['timeout']['max_ms'] == 100
    assert result['failures_by_category']['invalid_output']['max_ms'] == 200


def test_interrupted_pending_and_unstarted_are_distinct():
    result = summarize_group([None] * 4, [None] * 3, [record('success', 5), record('interrupted', 99)])
    assert result['counts'] == dict(planned=4, started=3, finished=2, completed=1,
                                    success=1, failed=0, interrupted=1, pending=1, not_started=1)
    assert result['success_rate'] == pytest.approx(1 / 3)
    assert result['provisional']
    assert result['success_ms']['n'] == result['completed_ms']['n'] == 1
    assert result['failure_ms']['n'] == 0
    assert result['interrupted_wait_ms']['max_ms'] == 99


def test_no_started_requests_does_not_claim_zero_percent_success():
    result = summarize_group([None], [], [])
    assert result['success_rate'] is None
    assert result['success_ms']['p95_ms'] is None
    assert result['counts']['not_started'] == 1
