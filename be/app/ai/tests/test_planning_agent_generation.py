"""채팅 graph와 생성 graph를 함께 실행해 권유·수락·현재 조건 보존을 검증한다."""

import asyncio
import json
from functools import partial

from langchain_core.messages import AIMessage, ToolMessage

from app.ai.errors import AITimeoutError
from app.ai.features.planning.agent.generation_tools import latest_reference_facts
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import GENERATE_TOOL_NAME, OFFER_TOOL_NAME, agent_tool_schemas
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput, PlanningAgentTurnResult
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.generation.schemas import PlanningGenerationState
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage
from app.ai.tests.test_plan_generation_graph import Model


def request(text="날짜는 나중에 정하자", id="u1", **changes):
    data=dict(draft=PlanningDraft(conditions=PlanningConditions(event_type="MT",headcount=50,fee_per_person=25000)),
              current_message=PlanningMessage(id=id,role="user",text=text),reference_date="2026-10-24")
    data.update(changes)
    return PlanningAgentTurnInput(**data)


def call(name, args, id="t1"):
    return dict(name=name,args=args,id=id)


def offer_call(id="t1"):
    return call(OFFER_TOOL_NAME,dict(action="offer",reason="날짜 없이 준비 순서를 잡을 수 있어요"),id)


def gen_call(req, id=None, **extra):
    return call(GENERATE_TOOL_NAME,dict(quote=req.current_message.text,**extra),
                id or "g-"+req.current_message.id)


def change_call(req, field, value, id=None):
    return call("update_event_conditions",dict(changes=[dict(op="SET",change=dict(field=field,value=value),status="specified",
        evidence=dict(message_id=req.current_message.id,quote=req.current_message.text))]),id or "c-"+req.current_message.id)


def run(req, responses, *, model=None, enabled=True):
    seen=[]
    model=model or Model()
    async def agent(messages, *, allow_tools):
        seen.append((messages,allow_tools))
        return responses[len(seen)-1]
    result=asyncio.run(run_planning_agent_turn(req,invoke=agent,
        generate=partial(run_plan_generation,invoke=model) if enabled else None))
    return result,seen,model


def next_request(first, text="응, 만들어줘", **extra):
    id="u"+str(1+sum(m.type=="human" for m in first.history))
    return request(text,id=id,draft=first.draft,history=first.history,generation=first.generation,**extra)


def make_offer():
    return run(request(),[AIMessage(content="",tool_calls=[offer_call()]),
                         AIMessage(content="날짜를 비우고 준비 순서를 먼저 잡아볼까요?")])[0]


def test_offer_does_not_generate_and_acceptance_uses_current_offer_and_real_subgraph():
    first=make_offer()
    assert first.generation.offer.status=="pending" and first.generation.preview is None
    assert first.generation_result is None and first.generation_model_calls==0
    req=next_request(first)
    before=req.model_dump_json()
    result,seen,model=run(req,[AIMessage(content="",tool_calls=[gen_call(req,offer_id=first.generation.offer.id)]),
                             AIMessage(content="날짜는 미정으로 두고 준비 순서를 만들었어요.")])
    assert result.generation_result.status=="generated" and result.preview_is_current
    assert result.generation.preview.trigger.source=="chat" and result.generation.offer is None
    assert result.generation.preview.basis_draft==req.draft and len(model.calls)==1
    assert result.model_calls==2 and result.generation_model_calls==1
    assert "generated" in seen[-1][0][-1].content
    assert req.model_dump_json()==before
    assert PlanningAgentTurnResult.model_validate_json(result.model_dump_json())==result
    restored=PlanningAgentTurnInput.model_validate_json(next_request(result,text="고마워").model_dump_json())
    assert restored.generation.preview==result.generation.preview


def test_defer_rejects_reoffer_but_explicit_generation_is_allowed():
    first=make_offer()
    req=next_request(first,text="아직 만들지 말자")
    defer=call(OFFER_TOOL_NAME,dict(action="defer",reason="더 이야기하기",
        evidence=dict(message_id="u2",quote="아직 만들지 말자")),"d1")
    result,_,model=run(req,[AIMessage(content="",tool_calls=[defer,offer_call("t2")]),AIMessage(content="더 의논해요.")])
    assert result.generation.offer.status=="deferred" and result.executions[-1].result.status=="rejected"
    assert not model.calls
    req=request("이제 바로 만들어줘",id="u3",draft=result.draft,history=result.history,generation=result.generation)
    generated,_,_=run(req,[AIMessage(content="",tool_calls=[gen_call(req)]),AIMessage(content="초안을 만들었어요.")])
    assert generated.generation_result.status=="generated"


def test_stale_offer_cannot_generate_after_conditions_changed():
    first=make_offer()
    req=next_request(first,text="40명으로 바꾸고, 아까 그 제안 좋네")
    result,_,model=run(req,[AIMessage(content="",tool_calls=[change_call(req,"headcount",40),
        gen_call(req,offer_id=first.generation.offer.id)]),AIMessage(content="40명 기준으로 만들지 확인할게요.")])
    assert result.draft.conditions.headcount==40 and not model.calls
    assert result.generation_result.status=="needs_clarification"
    assert "바뀌었어요" in result.generation_result.reason


def test_direct_mixed_request_changes_conditions_then_generates_without_new_confirmation():
    req=request("40명으로 바꾸고 바로 만들어줘")
    result,_,model=run(req,[AIMessage(content="",tool_calls=[change_call(req,"headcount",40),gen_call(req)]),
                           AIMessage(content="40명 기준으로 만들었어요.")])
    assert result.draft.conditions.headcount==result.generation.preview.basis_draft.conditions.headcount==40
    assert json.loads(model.calls[0][0][1].content)["basis_draft"]["conditions"]["headcount"]==40


def test_failed_date_change_blocks_generation_and_other_field_does_not_clear_it():
    req=request("시작을 4월로 바꾸고 만들어줘",draft=PlanningDraft(conditions=PlanningConditions(
        event_type="MT",start_date="2027-03-20",end_date="2027-03-21")))
    first,_,model=run(req,[AIMessage(content="",tool_calls=[change_call(req,"start_date","2027-04-20"),gen_call(req)]),
                         AIMessage(content="날짜 변경을 반영하지 못했어요.")])
    assert first.generation.condition_change_pending and not model.calls
    assert first.generation.pending_condition_fields==("start_date",)
    req=next_request(first,text="참가비는 3만 원, 일단 만들어줘")
    second,_,model=run(req,[AIMessage(content="",tool_calls=[change_call(req,"fee_per_person",30000),gen_call(req)]),
                          AIMessage(content="날짜 변경을 확인해야 해요.")])
    assert second.generation.condition_change_pending and not model.calls
    assert second.draft.conditions.fee_per_person==30000
    req=request("날짜는 지금 남은 조건으로 만들자",id="u3",draft=second.draft,history=second.history,generation=second.generation)
    third,_,_=run(req,[AIMessage(content="",tool_calls=[gen_call(req,use_current_conditions=True)]),AIMessage(content="현재 날짜로 만들었어요.")])
    assert third.generation_result.status=="generated" and not third.generation.condition_change_pending


def test_successful_same_field_correction_clears_pending_change():
    state=PlanningGenerationState(condition_change_pending=True,pending_condition_fields=("headcount",))
    req=request("인원은 40명으로 다시 정하자",generation=state)
    result,_,_=run(req,[AIMessage(content="",tool_calls=[change_call(req,"headcount",40)]),AIMessage(content="40명으로 반영했어요.")])
    assert not result.generation.condition_change_pending and not result.generation.pending_condition_fields


def test_wrong_evidence_and_wrong_offer_id_skip_generation():
    req=request("직접 만들어줘")
    bad=gen_call(req)
    bad["args"]["quote"]="이번 발화에 없는 문구"
    result,_,model=run(req,[AIMessage(content="",tool_calls=[bad,gen_call(req,id="g2",offer_id="unknown")]),
                          AIMessage(content="요청을 확인해 주세요.")])
    assert all(x.result.status=="needs_clarification" for x in result.executions) and not model.calls


def test_generation_tool_does_not_ask_model_to_copy_current_message_id():
    schema=next(x for x in agent_tool_schemas(search_enabled=False,generation_enabled=True)
                if x["function"]["name"]==GENERATE_TOOL_NAME)
    fields=schema["function"]["parameters"]["properties"]
    assert "quote" in fields and "evidence" not in fields and "message_id" not in fields
    req=request("응, 그 초안 만들어줘.",id="af53982f-0cbb-4d97-8cbd-35677f7adc66")
    result,_,_=run(req,[AIMessage(content="",tool_calls=[gen_call(req)]),AIMessage(content="초안이에요.")])
    assert result.generation.preview.trigger.request_id==req.current_message.id


def test_conversation_without_generation_call_does_not_create_or_change_preview():
    req=request("참가비 3만 원이면 어때?")
    result,_,model=run(req,[AIMessage(content="숙박과 이동 비용을 먼저 살펴보면 좋겠어요.")])
    assert result.generation==req.generation and result.generation_result is None and not model.calls


def test_failure_keeps_previous_preview_and_updated_conditions_marks_it_stale():
    req=request("만들어줘")
    first,_,_=run(req,[AIMessage(content="",tool_calls=[gen_call(req)]),AIMessage(content="초안이에요.")])
    req=next_request(first,text="40명으로 바꾸고 다시 만들어줘")
    result,_,_=run(req,[AIMessage(content="",tool_calls=[change_call(req,"headcount",40),gen_call(req)]),
                       AIMessage(content="40명은 반영했고 초안 생성은 실패했어요.")],model=Model(AITimeoutError("provider-detail")))
    assert result.draft.conditions.headcount==40 and result.generation.preview==first.generation.preview
    assert result.generation_result.status=="failed" and not result.preview_is_current
    assert "provider-detail" not in result.model_dump_json()


def test_generation_is_only_exposed_when_injected_and_shares_tool_limit():
    assert len(agent_tool_schemas(search_enabled=False,generation_enabled=True))==3
    assert len(agent_tool_schemas(search_enabled=True,generation_enabled=True))==4
    req=request("만들어줘")
    result,_,model=run(req,[AIMessage(content="",tool_calls=[gen_call(req)]),AIMessage(content="연결되지 않았어요.")],enabled=False)
    assert result.generation_result.status=="needs_clarification" and not model.calls
    model=Model(AITimeoutError("detail"))
    result,seen,model=run(req,[AIMessage(content="",tool_calls=[gen_call(req,id=f"g{i}") for i in range(4)]),
                             AIMessage(content="다음에 다시 시도해 주세요.")],model=model)
    assert len(model.calls)==result.generation_model_calls==3
    assert result.limit_reached and seen[-1][1] is False
    assert result.executions[-1].result.status=="needs_clarification"


def test_schema_arguments_reject_unrecognized_generation_fields():
    req=request("만들어줘")
    bad=gen_call(req,club_id="other-club")
    result,_,model=run(req,[AIMessage(content="",tool_calls=[bad]),AIMessage(content="인자를 확인해 주세요.")])
    assert result.generation_result.status=="needs_clarification" and not model.calls


def test_latest_failed_or_conflicting_lookup_is_not_replaced_by_old_success():
    old=ToolMessage(name="search_past_events",tool_call_id="s1",content=json.dumps(dict(status="available",query="과거",result={
        "facts":[dict(content="과거 비용",sources=[dict(record_id="r1",file_name="과거.pdf",location=dict(label="1쪽"))])]})))
    assert latest_reference_facts([old])[0].content=="과거 비용"
    failed=ToolMessage(name="search_past_events",tool_call_id="s2",content='{"status":"failed","reason":"확인 불가"}')
    assert latest_reference_facts([old,failed])==()
