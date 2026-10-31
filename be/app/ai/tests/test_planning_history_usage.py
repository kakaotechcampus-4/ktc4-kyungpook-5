"""#194: 이력 안내가 실제 저장 상태와 일치하고 기존 실패 경계를 유지하는지 확인한다."""
import json
from functools import partial

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.ai import (
    PlanningHistoryUsage, PlanningPublicResult, PlanningResumeState, PlanningStateError,
    chat_planning, generate_planning_preview, parse_resume_state,
)
from app.ai.contracts import MAX_PLANNING_HISTORY
from app.ai.features.planning import public_workflow as workflow
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.tests.test_plan_generation_graph import Model
from app.ai.tests.test_planning_public_workflow import request, button, scripted, tool, run
from app.ai.features.planning.agent.nodes import TOOL_NAME


def state_with_history(req, count):
    """완료된 상담을 번갈아 배치한다. Tool 이력은 실제 Graph 경로로 따로 검증한다."""
    return PlanningResumeState(
        club_id=req.club_id, event_id=req.event_id, conversation_id=req.conversation_id,
        payload=dict(basis_draft=req.draft, history=[
            dict(role='user' if i % 2 == 0 else 'assistant', id=f'prior-{i}', content='이전 상담')
            for i in range(count)
        ]),
    )


@pytest.mark.parametrize('count,near', [(0,False),(47,False),(48,True),(59,True),(60,True)])
def test_usage_boundaries_and_json(count, near):
    usage=PlanningHistoryUsage.from_count(count)
    assert usage.model_dump()==dict(message_count=count,max_messages=60,near_limit=near)
    assert PlanningHistoryUsage.model_validate_json(usage.model_dump_json())==usage


@pytest.mark.parametrize('count', [-1,61,True,1.5,'48'])
def test_invalid_counts_are_not_silently_converted(count):
    with pytest.raises((ValidationError, TypeError)):
        PlanningHistoryUsage.from_count(count)


@pytest.mark.parametrize('data', [
    dict(message_count=47,near_limit=True),
    dict(message_count=48,near_limit=False),
    dict(message_count=48,max_messages=100,near_limit=True),
])
def test_usage_rejects_misleading_flag_or_limit(data):
    with pytest.raises(ValidationError):
        PlanningHistoryUsage(**data)


@pytest.mark.parametrize('before,after,near', [(44,46,False),(46,48,True),(58,60,True)])
def test_chat_without_condition_change_counts_after_the_turn(monkeypatch,before,after,near):
    req=request()
    req=request(resume_state=state_with_history(req,before))
    saved=req.model_dump_json()
    scripted(monkeypatch,[AIMessage(content='정한 내용은 그대로 둘게요.')])
    result=run(chat_planning(req))
    assert result.view.changed_fields==()
    assert result.view.draft==req.draft
    assert result.view.history_usage.message_count==after
    assert result.view.history_usage.near_limit is near
    assert result.view.history_usage.message_count==len(result.next_state.payload.history)
    assert req.model_dump_json()==saved


def test_tool_messages_and_roundtrip_then_button_share_the_same_usage(monkeypatch):
    req=request()
    req=request(resume_state=state_with_history(req,44))
    scripted(monkeypatch,[tool(TOOL_NAME,{'changes':[
        dict(op='SET',change=dict(field='headcount',value=50),status='tentative',
             evidence=dict(message_id='u1',quote='대략 50명으로 잡자'))]}),
        AIMessage(content='50명을 잠정으로 반영했어요.')])
    result=run(chat_planning(req))
    assert result.view.history_usage.message_count==48
    assert result.view.history_usage.near_limit
    assert [m.role for m in result.next_state.payload.history[-4:]]==['user','assistant','tool','assistant']
    saved=parse_resume_state(result.next_state.model_dump_json())
    assert saved.schema_version==1
    assert set(json.loads(saved.model_dump_json())['payload'])=={'basis_draft','history','generation'}
    assert PlanningPublicResult.model_validate_json(result.model_dump_json())==result
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model()))
    generated=run(generate_planning_preview(button(req,draft=result.view.draft,resume_state=saved)))
    assert generated.view.generation_result.status=='generated'
    assert generated.view.history_usage==result.view.history_usage
    assert generated.next_state.payload.history==saved.payload.history


def test_multiple_tool_results_count_as_messages_not_user_turns(monkeypatch):
    req=request(resume_state=state_with_history(request(),44))
    # 잘못된 이름도 실행 결과 메시지가 남는다. 두 결과를 각각 세야 한다.
    scripted(monkeypatch,[AIMessage(content='',tool_calls=[
        dict(id='call-a',name='unsupported-a',args={}),dict(id='call-b',name='unsupported-b',args={})]),
        AIMessage(content='지원하지 않는 요청이라 조건은 유지했어요.')])
    result=run(chat_planning(req))
    assert result.view.history_usage.message_count==49
    assert result.view.draft==req.draft


@pytest.mark.parametrize('count',[0,48,60])
def test_button_never_increments_history_even_at_the_limit(monkeypatch,count):
    req=request()
    state=parse_resume_state(state_with_history(req,count).model_dump_json())
    monkeypatch.setattr(workflow,'run_plan_generation',partial(run_plan_generation,invoke=Model()))
    result=run(generate_planning_preview(button(req,resume_state=state)))
    assert result.view.history_usage.message_count==count
    assert result.next_state.payload.history==state.payload.history
    assert result.view.reply is None


def test_over_limit_after_a_tool_does_not_commit_partial_changes(monkeypatch):
    req=request(resume_state=state_with_history(request(),58))
    before=req.model_dump_json()
    scripted(monkeypatch,[tool(TOOL_NAME,{'changes':[
        dict(op='SET',change=dict(field='headcount',value=50),status='tentative',
             evidence=dict(message_id='u1',quote='대략 50명으로 잡자'))]}),AIMessage(content='반영했어요.')])
    with pytest.raises(PlanningStateError) as exc:
        run(chat_planning(req))
    assert exc.value.code=='history_limit'
    assert req.model_dump_json()==before
    assert req.draft.conditions.headcount is None
    assert len(req.resume_state.payload.history)==58


def test_public_result_rejects_usage_from_a_different_snapshot(monkeypatch):
    scripted(monkeypatch,[AIMessage(content='조건은 유지할게요.')])
    result=run(chat_planning(request()))
    data=result.model_dump(mode='json')
    data['view']['history_usage']['message_count']=0
    with pytest.raises(ValidationError,match='화면 이력 사용량'):
        PlanningPublicResult.model_validate(data)


def test_old_saved_view_has_unknown_usage_without_changing_state(monkeypatch):
    scripted(monkeypatch,[AIMessage(content='조건은 유지할게요.')])
    result=run(chat_planning(request()))
    data=result.model_dump(mode='json')
    data['view'].pop('history_usage')
    restored=PlanningPublicResult.model_validate(data)
    assert restored.view.history_usage is None
    assert restored.next_state==result.next_state
    assert MAX_PLANNING_HISTORY==60
