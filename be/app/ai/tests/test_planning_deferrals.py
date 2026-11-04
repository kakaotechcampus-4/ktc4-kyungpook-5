"""#205: 답변이 자연스러워도 보류 대상이 바뀌면 실패로 구분한다."""

import asyncio
from unittest.mock import patch

from langchain_core.messages import AIMessage
import pytest

from app.ai import chat_planning
from app.ai.features.planning.agent import graph
from app.ai.scripts.check_planning_deferrals import CASES, case_request, inspect_boundary, summarize
from app.ai.scripts.planning_latency_inputs import load_fixture


def execute(case, *, topics=(), status='specified', resume=True):
    req = case_request(load_fixture(), case, 'boundary-test')
    evidence = dict(message_id=req.message.id, quote=req.message.content)
    condition = dict(changes=[dict(op='SET', change=dict(field='headcount', value=60),
                                 status=status, evidence=evidence)],
                     defer_topics=[dict(topic=t, evidence=evidence) for t in topics])
    if case.start_state:  # 정정 발화에는 인원이 없다. 날짜 재개만 요청한다.
        condition['changes'] = []
    if resume and 'dates' in req.draft.deferred_topics and 'dates' not in topics:
        condition['resume_topics'] = [dict(topic='dates', evidence=evidence)]
    responses = iter([
        AIMessage(content='', tool_calls=[dict(id='conditions', name='update_event_conditions', args=condition)]),
        AIMessage(content='', tool_calls=[dict(id='offer', name='update_generation_offer',
            args=dict(action='defer', reason='초안은 나중에', evidence=evidence))]),
        AIMessage(content='인원을 60명으로 바꾸고 초안 생성은 보류했어요.'),
    ])
    async def model(*args, **kwargs):
        return next(responses)
    before = req.model_dump_json()
    with patch.object(graph, 'call_agent_model', model):
        result = asyncio.run(chat_planning(req))
    assert req.model_dump_json() == before
    return req, result


@pytest.mark.parametrize('status', ['tentative', 'specified'])
def test_headcount_status_is_diagnostic_and_not_boundary_failure(status):
    req, result = execute(CASES[0], status=status)
    observed = inspect_boundary(req, result, CASES[0])
    assert observed['passed'] and observed['headcount_status'] == status


def test_natural_reply_does_not_hide_an_extra_date_deferral():
    req, result = execute(CASES[0], topics=('dates',))
    observed = inspect_boundary(req, result, CASES[0])
    assert result.view.reply == '인원을 60명으로 바꾸고 초안 생성은 보류했어요.'
    assert observed['checks']['conditions_match'] and observed['checks']['no_generation']
    assert not observed['passed'] and observed['extra_topics'] == ['dates']


@pytest.mark.parametrize('index', [2, 3, 4, 5, 6, 7])
def test_legitimate_topic_deferral_and_resume_are_required(index):
    case = CASES[index]
    req, result = execute(case, topics=case.expected_topics)
    assert inspect_boundary(req, result, case)['passed']


def test_blocking_all_topic_changes_would_fail_a_legitimate_date_request():
    case = CASES[2]
    req, result = execute(case)
    observed = inspect_boundary(req, result, case)
    assert not observed['passed'] and observed['missing_topics'] == ['dates']


def test_each_request_restores_its_own_context_and_deferral_basis():
    fixture = load_fixture()
    original = fixture.model_dump_json()
    first = case_request(fixture, CASES[5], 'resume')
    second = case_request(fixture, CASES[0], 'plain')
    context = case_request(fixture, CASES[4], 'context')
    assert first.draft.deferred_topics == ('dates',)
    assert first.resume_state.payload.generation.offer.basis_draft == first.draft
    assert second.draft.deferred_topics == ()
    assert context.resume_state.payload.history[-1].content == CASES[4].previous_reply
    assert fixture.model_dump_json() == original


def test_correction_starts_from_the_saved_turn_that_deferred_dates_again():
    """#274: 정정 사례는 실제로 날짜를 다시 보류한 턴의 다음 상태에서 시작한다."""
    case = next(c for c in CASES if c.id == 'date_resume_correction')
    req = case_request(load_fixture(), case, 'correction')
    assert req.draft.conditions.headcount == 60 and req.draft.deferred_topics == ('dates',)
    assert req.resume_state.payload.generation.offer.status == 'deferred'
    assert '나중에' in req.resume_state.payload.history[-1].content[0]['text']
    assert req.message.content == case.text and req.message.id == 'correction-user'


@pytest.mark.parametrize('case_id', ['date_resume_clear', 'date_resume_correction'])
def test_keeping_the_date_deferral_fails_clear_resume_and_correction(case_id):
    case = next(c for c in CASES if c.id == case_id)
    req, result = execute(case, resume=False)
    observed = inspect_boundary(req, result, case)
    assert not observed['passed'] and observed['extra_topics'] == ['dates']


def test_summary_keeps_exceptions_and_semantic_failures_in_the_denominator():
    summary = summarize([
        dict(variant='candidate', case_id='generation_only', passed=True,
             checks={'topics_match': True}, headcount_status='tentative'),
        dict(variant='candidate', case_id='generation_only', passed=False,
             checks={'topics_match': False}, extra_topics=['dates'], headcount_status='specified'),
        dict(variant='candidate', case_id='generation_only', passed=False, error='timeout'),
    ])['candidate']['generation_only']
    assert summary['started'] == 3 and summary['passed'] == 1
    assert summary['extra_topic_requests'] == 1
    assert summary['errors'] == {'timeout': 1}
