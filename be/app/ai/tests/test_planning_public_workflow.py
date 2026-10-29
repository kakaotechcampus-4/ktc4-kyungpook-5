"""공개 함수로 실행하며 모델 응답만 고정한다. DB/네트워크는 사용하지 않는다."""
import asyncio
from functools import partial

import pytest
from langchain_core.messages import AIMessage

from app.ai import (chat_planning, generate_planning_preview, PlanningChatRequest,
    PlanningPreviewRequest, PlanningUserMessage, PlanningDraft, PlanningConditions,
    parse_resume_state, AITimeoutError)
from app.ai.features.planning import public_workflow as workflow
from app.ai.features.planning.agent import graph
from app.ai.features.planning.agent.nodes import TOOL_NAME, SEARCH_TOOL_NAME, GENERATE_TOOL_NAME, OFFER_TOOL_NAME
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.agent.record_tool import RecordLookupResult
from app.ai.features.retrieval.schemas import RecordSearchResult, RecordFact
from app.ai.contracts import RecordSource, SourceLocation
from app.ai.tests.test_plan_generation_graph import Model


def request(**extra):
    data = dict(request_id='r1', club_id='club1', event_id='event1', conversation_id='conv1',
        base_revision=3, draft=PlanningDraft(conditions=PlanningConditions(event_type='MT', fee_per_person=25000), deferred_topics=('dates', 'headcount', 'location')),
        reference_date='2026-10-25', message=PlanningUserMessage(id='u1', content='대략 50명으로 잡자'))
    data.update(extra)
    return PlanningChatRequest(**data)


def button(req, **extra):
    data=req.model_dump(exclude={'message'})
    data.update(extra)
    return PlanningPreviewRequest(**data)


def scripted(monkeypatch, responses):
    iterator=iter(responses)
    async def invoke(messages, **kwargs):
        value=next(iterator)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(graph, 'call_agent_model', invoke)


def tool(name, args, id='t1'):
    return AIMessage(content='', tool_calls=[dict(id=id, name=name, args=args)])


def run(coro):
    return asyncio.run(coro)


def test_public_chat_then_json_resume(monkeypatch):
    scripted(monkeypatch, [tool(TOOL_NAME, {'changes':[dict(op='SET', change=dict(field='headcount',value=50),
        status='tentative', evidence=dict(message_id='u1',quote='대략 50명으로 잡자'))]}), AIMessage(content='50명으로 잡았어요.'),
        AIMessage(content='다음 조건을 이야기해 주세요.')])
    req=request()
    original=req.model_dump_json()
    first=run(chat_planning(req))
    assert first.view.draft.conditions.headcount==50
    assert first.view.changed_fields==('headcount',)
    assert first.view.generation_readiness.can_generate
    assert first.base_revision==3
    assert original==req.model_dump_json()
    state=parse_resume_state(first.next_state.model_dump_json())
    next_req=request(request_id='r2', draft=first.view.draft, resume_state=state,
        message=PlanningUserMessage(id='u2',content='좋아'))
    second=run(chat_planning(next_req))
    assert second.view.changed_fields==()
    assert len(second.next_state.payload.history)==6


def test_button_success_reuse_and_no_fake_message(monkeypatch):
    model=Model()
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=model))
    first=run(generate_planning_preview(button(request())))
    assert first.view.reply is None
    assert first.view.generation_result.status=='generated'
    assert first.view.preview_is_current
    assert first.next_state.payload.history==()
    second=run(generate_planning_preview(button(request(),resume_state=parse_resume_state(first.next_state.model_dump_json()))))
    assert second.view.generation_result.preview.id==first.view.generation_result.preview.id
    assert len(model.calls)==1


def test_missing_type_does_not_call_model(monkeypatch):
    async def unexpected(*args,**kwargs):
        pytest.fail('생성 모델 호출 금지')
    monkeypatch.setattr(workflow,'run_plan_generation',unexpected)
    result=run(generate_planning_preview(button(request(draft=PlanningDraft()))))
    assert result.view.generation_readiness.reasons==('event_type_missing',)
    assert result.view.generation_result.status=='needs_clarification'


def test_failed_generation_preserves_previous_preview(monkeypatch):
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model()))
    first=run(generate_planning_preview(button(request())))
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model(AITimeoutError('timeout'))))
    second=run(generate_planning_preview(button(request(),request_id='new-click',resume_state=first.next_state)))
    assert second.view.generation_result.status=='failed'
    assert second.next_state.payload.generation.preview==first.next_state.payload.generation.preview
    assert second.view.generation_result.preview is None


def test_whole_chat_failure_does_not_mutate_input(monkeypatch):
    scripted(monkeypatch,[AITimeoutError('timeout')])
    req=request()
    before=req.model_dump_json()
    with pytest.raises(AITimeoutError):
        run(chat_planning(req))
    assert before==req.model_dump_json()


def test_offer_acceptance_after_restore_generates(monkeypatch):
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model()))
    scripted(monkeypatch,[tool(OFFER_TOOL_NAME,dict(action='offer',reason='현재 조건으로 만들까요?')),
        AIMessage(content='초안을 만들까요?')])
    first=run(chat_planning(request()))
    offer=first.next_state.payload.generation.offer
    assert first.view.generation_result is None
    scripted(monkeypatch,[tool(GENERATE_TOOL_NAME,dict(quote='응 만들어줘',offer_id=offer.id),id='gen2'),
        AIMessage(content='초안을 만들었어요.')])
    second=run(chat_planning(request(request_id='r2',resume_state=parse_resume_state(first.next_state.model_dump_json()),
        message=PlanningUserMessage(id='u2',content='응 만들어줘'))))
    assert second.view.generation_result.status=='generated'
    assert second.view.generation_result.preview.trigger.source=='chat'


def test_search_scope_and_reference_survive_button_restore(monkeypatch):
    seen=[]
    port=object()
    fact=RecordFact(content='작년 참가비 45000원', sources=(RecordSource(record_id='record1',
        file_name='장부',location=SourceLocation(label='Sheet1 2행')),))
    async def search(arguments,draft,reference_date,*,club_id,port):
        seen.append((club_id,port))
        return RecordLookupResult(status='available',query=arguments.query,result=RecordSearchResult(facts=(fact,)))
    monkeypatch.setattr(workflow,'search_past_events',search)
    scripted(monkeypatch,[tool(SEARCH_TOOL_NAME,dict(query='작년 참가비')),
        AIMessage(content='작년에는 45000원이었어요.')])
    first=run(chat_planning(request(),records=port))
    assert seen==[('club1',port)]
    assert first.view.draft.conditions.fee_per_person==25000
    state=parse_resume_state(first.next_state.model_dump_json())
    assert any(m.name==SEARCH_TOOL_NAME for m in state.payload.history)
    async def generate(req):
        assert req.reference_facts==(fact,)
        return await run_plan_generation(req,invoke=Model())
    monkeypatch.setattr(workflow,'run_plan_generation',generate)
    second=run(generate_planning_preview(button(request(),resume_state=state)))
    assert second.next_state.payload.history==state.payload.history
    assert second.view.generation_result.status=='generated'


def test_search_partial_failure_retains_chat(monkeypatch):
    async def search(*args,**kwargs):
        return RecordLookupResult(status='failed',reason='검색 실패')
    monkeypatch.setattr(workflow,'search_past_events',search)
    scripted(monkeypatch,[tool(SEARCH_TOOL_NAME,dict(query='작년 참가비')),AIMessage(content='조회에 실패했어요.')])
    result=run(chat_planning(request(),records=object()))
    assert result.view.record_lookup.status=='failed'
    assert result.view.draft==request().draft
    assert result.view.reply=='조회에 실패했어요.'


def test_condition_success_and_generation_failure_are_separate(monkeypatch):
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model(AITimeoutError('timeout'))))
    scripted(monkeypatch,[tool(TOOL_NAME, {'changes':[dict(op='SET',change=dict(field='headcount',value=50),
        status='tentative',evidence=dict(message_id='u1',quote='50명으로 만들자'))]}),
        tool(GENERATE_TOOL_NAME,dict(quote='50명으로 만들자'),id='g1'),AIMessage(content='인원은 반영했지만 생성은 실패했어요.')])
    result=run(chat_planning(request(message=PlanningUserMessage(id='u1',content='50명으로 만들자'))))
    assert result.view.generation_result.status=='failed'
    assert result.view.draft.conditions.headcount==50
    assert result.next_state.payload.basis_draft==result.view.draft


def test_pending_change_requires_explicit_override(monkeypatch):
    scripted(monkeypatch,[tool(TOOL_NAME, {'changes':[dict(op='SET',change=dict(field='headcount',value=-1),
        status='specified',evidence=dict(message_id='u1',quote='인원 -1명'))]}),AIMessage(content='인원은 양수여야 해요.')])
    first=run(chat_planning(request(message=PlanningUserMessage(id='u1',content='인원 -1명'))))
    assert first.view.generation_readiness.reasons==('condition_change_pending',)
    model=Model()
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=model))
    blocked=run(generate_planning_preview(button(request(),resume_state=first.next_state)))
    assert blocked.view.generation_result.status=='needs_clarification'
    assert not model.calls
    allowed=run(generate_planning_preview(button(request(),resume_state=first.next_state,use_current_conditions=True)))
    assert allowed.view.generation_result.status=='generated'
    assert allowed.view.generation_readiness.can_generate


def test_without_records_search_tool_is_disabled(monkeypatch):
    async def model(messages, *, search_enabled, generation_enabled, **kwargs):
        assert search_enabled is False
        assert generation_enabled is True
        return AIMessage(content='조건을 이야기해 주세요.')
    monkeypatch.setattr(graph,'call_agent_model',model)
    assert run(chat_planning(request())).view.record_lookup is None


def test_unanswered_topics_block_button_then_explicit_deferrals_survive_restore(monkeypatch):
    from app.ai.features.planning.generation.readiness import generation_blocks
    from app.ai.features.planning.generation.schemas import PlanningGenerationState
    draft = PlanningDraft(conditions=PlanningConditions(event_type="MT"))
    assert generation_blocks(draft, PlanningGenerationState()) == (
        "dates_unanswered", "headcount_unanswered", "location_unanswered")
    async def unexpected(*args, **kwargs):
        pytest.fail("미답변 상태에서 생성 모델을 호출하면 안 됩니다")
    monkeypatch.setattr(workflow, "run_plan_generation", unexpected)
    blocked = run(generate_planning_preview(button(request(draft=draft))))
    assert blocked.view.generation_result.status == "needs_clarification"
    assert blocked.view.generation_readiness.reasons[0] == "dates_unanswered"
    answered = PlanningDraft(conditions=PlanningConditions(event_type="MT", headcount=40),
                             deferred_topics=("dates", "location"))
    restored = PlanningDraft.model_validate_json(answered.model_dump_json())
    assert restored.conditions.start_date is None and restored.conditions.location is None
    assert generation_blocks(restored, PlanningGenerationState()) == ()
    assert generation_blocks(restored, PlanningGenerationState(condition_change_pending=True),
                             use_current_conditions=True) == ()


def test_readiness_recomputed_for_restored_state_and_rejects_mismatch(monkeypatch):
    from app.ai import planning_generation_readiness, PlanningStateError
    scripted(monkeypatch, [AIMessage(content='일정을 알려주세요.')])
    initial = PlanningDraft(conditions=PlanningConditions(event_type='MT'))
    result = run(chat_planning(request(draft=initial)))
    restored = parse_resume_state(result.next_state.model_dump_json())
    assert planning_generation_readiness(initial, resume_state=restored).reasons == (
        'dates_unanswered', 'headcount_unanswered', 'location_unanswered')
    with pytest.raises(PlanningStateError):
        planning_generation_readiness(PlanningDraft(), resume_state=restored)
