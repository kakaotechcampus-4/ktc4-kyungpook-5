"""같은 검증 기준에서 첫 위반의 위치·기대/실제 값만 추가되는지 확인한다."""

import asyncio

import pytest

import app.ai as ai
from app.ai.errors import AIInvalidResponseError
from app.ai.features.planning.generation.graph import run_plan_generation, validate_plan
from app.ai.features.planning.generation.validation import MESSAGES, PlanValidationError, PlanValidationViolation
from app.ai.tests.test_plan_generation_graph import composition, request, Model


def dated_request():
    return request(basis_draft=ai.PlanningDraft(conditions=ai.PlanningConditions(
        event_type='WORKSHOP', start_date='2026-11-07', end_date='2026-11-07')))


def examples():
    step = lambda code, **kwargs: dict(code=code, purpose='합성 검증 사례', **kwargs)
    return [
        ('catalog_partition', '', request(), composition(excluded_steps=[])),
        ('phase_order', '/steps', request(), composition(steps=[step('EVENT_DAY'), step('RESEARCH_VENUE')])),
        ('reversed_period', '/steps/0/deadline', dated_request(), composition(steps=[step('RESEARCH_VENUE',
            starts_at='2026-11-06T09:00:00+09:00', deadline='2026-11-05T09:00:00+09:00')])),
        ('dates_when_unknown', '/steps/0/starts_at', request(), composition(steps=[step('RESEARCH_VENUE',
            starts_at='2026-11-06T09:00:00+09:00')])),
        ('action_type', '/steps/0/actions/0/type', dated_request(), composition(steps=[step('RESEARCH_VENUE',
            actions=[dict(type='NOTICE', title='허용되지 않은 행동')])])),
        ('action_due_outside_step', '/steps/0/actions/0/due_date', dated_request(), composition(steps=[step('RECRUIT_NOTICE',
            starts_at='2026-11-03T09:00:00+09:00', deadline='2026-11-04T18:00:00+09:00',
            actions=[dict(type='NOTICE', title='모집 안내', due_date='2026-11-05')])])),
        ('before_event_after_start', '/steps/0/deadline', dated_request(), composition(steps=[step('RESEARCH_VENUE',
            deadline='2026-11-08T09:00:00+09:00')])),
        ('event_start_mismatch', '/steps/0/starts_at', dated_request(), composition(steps=[step('EVENT_DAY',
            starts_at='2026-11-08T09:00:00+09:00')])),
        ('event_end_mismatch', '/steps/0/deadline', dated_request(), composition(steps=[step('EVENT_DAY',
            starts_at='2026-11-07T09:00:00+09:00', deadline='2026-11-08T18:00:00+09:00')])),
        ('after_event_before_end', '/steps/0/starts_at', dated_request(), composition(steps=[step('SETTLE_EXPENSES',
            starts_at='2026-11-06T09:00:00+09:00')])),
        ('unknown_fact_id', '/assumptions/0/fact_ids/0', dated_request(),
            composition(assumptions=[dict(content='없는 근거', fact_ids=['f999'])])),
    ]


@pytest.mark.parametrize('rule,path,req,answer', examples(), ids=[x[0] for x in examples()])
def test_all_rules_report_first_location_and_preserve_original_message(rule, path, req, answer):
    before = (req.model_dump_json(), answer.model_dump_json())
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=req, composition=answer))
    error = caught.value
    assert isinstance(error, AIInvalidResponseError)
    assert error.violation.rule == rule and error.violation.path == path
    assert str(error) == MESSAGES[rule]
    assert PlanValidationViolation.model_validate_json(error.violation.model_dump_json()) == error.violation
    assert before == (req.model_dump_json(), answer.model_dump_json())
    assert set(MESSAGES) == {x[0] for x in examples()}


def test_event_day_example_has_real_values_and_original_timestamp():
    _, _, req, answer = next(x for x in examples() if x[0] == 'event_start_mismatch')
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=req, composition=answer))
    data = caught.value.violation.model_dump(mode='json')
    assert data == dict(rule='event_start_mismatch', path='/steps/0/starts_at', step_code='EVENT_DAY',
        action_index=None, expected='2026-11-07',
        actual=dict(timestamp='2026-11-08T09:00:00+09:00', local_date='2026-11-08'), timezone='Asia/Seoul')


def test_timezone_is_applied_before_comparing_dates():
    req = dated_request()
    answer = composition(steps=[dict(code='EVENT_DAY', purpose='한국 기준 11월 7일',
                                    starts_at='2026-11-06T16:00:00+00:00')])
    assert validate_plan(dict(request=req, composition=answer))['preview'].steps
    answer = composition(steps=[dict(code='EVENT_DAY', purpose='한국 기준 11월 8일',
                                    starts_at='2026-11-07T16:00:00+00:00')])
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=req, composition=answer))
    assert caught.value.violation.actual == dict(timestamp='2026-11-07T16:00:00+00:00', local_date='2026-11-08')


def test_first_rule_order_is_preserved_even_with_multiple_violations():
    answer = composition(steps=[dict(code='EVENT_DAY', purpose='역전과 날짜 문제',
        starts_at='2026-11-09T09:00:00+09:00', deadline='2026-11-08T09:00:00+09:00')])
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=dated_request(), composition=answer))
    assert caught.value.violation.rule == 'reversed_period'
    broken_catalog = answer.model_copy(update={'excluded_steps': ()})
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=dated_request(), composition=broken_catalog))
    assert caught.value.violation.rule == 'catalog_partition'


def test_unknown_date_checks_action_due_date_and_known_end_can_remain_unknown():
    answer = composition(steps=[dict(code='RECRUIT_NOTICE', purpose='모집',
        actions=[dict(type='NOTICE', title='모집', due_date='2026-11-05')])])
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=request(), composition=answer))
    assert caught.value.violation.path == '/steps/0/actions/0/due_date'
    assert caught.value.violation.expected is None and caught.value.violation.actual == '2026-11-05'
    req = request(basis_draft=ai.PlanningDraft(conditions=ai.PlanningConditions(event_type='MT', start_date='2026-11-07')))
    answer = composition(steps=[dict(code='EVENT_DAY', purpose='당일', deadline='2026-11-07T18:00:00+09:00')])
    with pytest.raises(PlanValidationError) as caught:
        validate_plan(dict(request=req, composition=answer))
    assert caught.value.violation.rule == 'event_end_mismatch' and caught.value.violation.expected is None


def test_public_failure_and_logs_do_not_expose_validation_values(caplog):
    _, _, req, answer = next(x for x in examples() if x[0] == 'event_start_mismatch')
    result = asyncio.run(run_plan_generation(req, invoke=Model(answer)))
    assert result.status == 'failed'
    assert result.reason == '생성된 초안이 단계·날짜·근거 검증을 통과하지 못했어요. 다시 시도해 주세요.'
    assert 'stage=validate_plan code=invalid_plan' in caplog.text
    assert '2026-11-08' not in result.model_dump_json() + caplog.text
    assert 'event_start_mismatch' not in result.model_dump_json() + caplog.text
    assert not hasattr(ai, 'PlanValidationError')
