"""새 Agent에서 기존 retrieval을 그대로 거쳐 검색·현재 조건 변경을 구분한다."""

import asyncio
from functools import partial

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from app.ai.errors import AIConfigError, AITimeoutError
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import SEARCH_TOOL_NAME, agent_tool_schemas
from app.ai.features.planning.agent.record_tool import RecordLookupResult, SearchPastEventsInput, search_past_events
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput, PlanningAgentTurnResult
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage
from app.ai.features.retrieval.schemas import EvidenceAssessment
from app.ai.tests.test_planning_records import Model, Port, chunk, embed


def request(**changes):
    data = dict(draft=PlanningDraft(conditions=PlanningConditions(event_type="MT", fee_per_person=25000,
        headcount=50, location="올해 장소", start_date="2026-11-01")),
        current_message=PlanningMessage(id="u1",role="user",text="2025년 봄 MT 참가비는 얼마였어?"),
        reference_date="2026-10-24")
    data.update(changes)
    return PlanningAgentTurnInput(**data)


def search_call(call_id="s1", **args):
    return dict(id=call_id,name=SEARCH_TOOL_NAME,args={"query":"2025 봄 MT 참가비",**args})


def lookup(port, model=None):
    model = model or Model(EvidenceAssessment(sufficient=True,retry_queries=[],
        facts=[{"content":"2025 봄 MT 참가비 45,000원","chunk_ids":["c1"]}],not_found=[],conflicts=[]))
    return partial(search_past_events,club_id="server-club",port=port,embed=embed,invoke=model)


def run(req, responses, search):
    observed=[]
    async def invoke(messages, *, allow_tools):
        observed.append(messages)
        return responses[len(observed)-1]
    result=asyncio.run(run_planning_agent_turn(req,invoke=invoke,search=search))
    return result,observed


def test_search_reuses_retrieval_scope_and_preserves_draft_and_sources():
    port=Port((chunk("report","참가비 45,000원"),))
    req=request()
    before=req.model_dump_json()
    result,seen=run(req,[AIMessage(content="",tool_calls=[search_call()]),AIMessage(content="작년 봄은 45,000원이었어요.")],lookup(port))
    assert result.draft==req.draft and req.model_dump_json()==before
    assert result.record_lookup.status=="available"
    assert result.record_lookup.result.facts[0].sources==(port.chunks[0].source,)
    assert port.calls[0].club_id=="server-club" and port.calls[0].event_id is None
    assert port.calls[0].category is None
    assert isinstance(seen[1][-1],ToolMessage)
    assert "45,000원" in seen[1][-1].content
    assert PlanningAgentTurnResult.model_validate_json(result.model_dump_json())==result


def test_search_then_acceptance_uses_update_tool_on_next_turn():
    first,_=run(request(),[AIMessage(content="",tool_calls=[search_call()]),AIMessage(content="2025 봄은 45,000원이었어요.")],
                lookup(Port((chunk("report","45,000원"),))))
    next_request=request(draft=first.draft,history=first.history,
        current_message=PlanningMessage(id="u2",role="user",text="올해도 그 금액으로 하자"))
    change=dict(id="c1",name="update_event_conditions",args={"changes":[dict(op="SET",
        change={"field":"fee_per_person","value":45000},status="specified",
        evidence={"message_id":"u2","quote":"올해도 그 금액으로 하자"})]})
    second,seen=run(next_request,[AIMessage(content="",tool_calls=[change]),AIMessage(content="45,000원으로 반영했어요.")],None)
    assert first.draft.conditions.fee_per_person==25000
    assert second.draft.conditions.fee_per_person==45000
    assert second.record_lookup is None  # 새 조회가 없다는 뜻. 이전 출처는 history에 남아 있다.
    assert any(isinstance(m,ToolMessage) and "45,000원" in m.content for m in seen[0])


def test_no_records_is_normal_not_found_and_does_not_change_conditions():
    result,_=run(request(),[AIMessage(content="",tool_calls=[search_call()]),AIMessage(content="기록을 찾지 못했어요.")],lookup(Port(),Model()))
    assert result.record_lookup.status=="not_found"
    assert result.record_lookup.result.not_found
    assert result.draft.conditions.fee_per_person==25000


def test_search_failure_preserves_condition_updated_earlier_in_same_batch():
    req=request(current_message=PlanningMessage(id="u1",role="user",text="인원은 40명으로, 작년 참가비도 찾아줘"))
    change=dict(id="c1",name="update_event_conditions",args={"changes":[dict(op="SET",
        change={"field":"headcount","value":40},status="specified",
        evidence={"message_id":"u1","quote":"인원은 40명으로"})]})
    result,_=run(req,[AIMessage(content="",tool_calls=[change,search_call()]),AIMessage(content="인원은 반영했고 검색은 실패했어요.")],
                 lookup(Port(error=AITimeoutError("provider detail"))))
    assert result.draft.conditions.headcount==40
    assert result.record_lookup.status=="failed" and result.record_lookup.result is None
    assert "provider detail" not in result.record_lookup.model_dump_json()


def test_partial_and_conflicting_evidence_are_preserved():
    chunks=(chunk("report","참가비 45,000원"),chunk("notice","참가비 40,000원"))
    model=Model(EvidenceAssessment(sufficient=False,retry_queries=["추가 검색"],facts=[],not_found=["교통비"],
        conflicts=[{"description":"참가비 차이","values":[{"content":"45,000원","chunk_ids":["c1"]},
                                                          {"content":"40,000원","chunk_ids":["c2"]}]}]))
    port=Port(chunks)
    result,_=run(request(),[AIMessage(content="",tool_calls=[search_call()]),AIMessage(content="자료에 차이가 있어요.")],lookup(port,model))
    evidence=result.record_lookup.result
    assert evidence.not_found==("교통비",)
    assert evidence.conflicts[0].values[1].sources==(chunks[1].source,)
    assert result.draft.conditions.fee_per_person==25000 and len(port.calls)==1


@pytest.mark.parametrize("error",[PermissionError("denied"),AIConfigError("config"),RuntimeError("unexpected")])
def test_permission_configuration_and_unexpected_errors_propagate(error):
    req=request()
    with pytest.raises(type(error)):
        run(req,[AIMessage(content="",tool_calls=[search_call()])],lookup(Port(error=error)))
    assert req.draft.conditions.fee_per_person==25000


def test_model_cannot_choose_club_or_inject_search_scope():
    port=Port()
    result,_=run(request(),[AIMessage(content="",tool_calls=[search_call(club_id="other")]),AIMessage(content="다시 확인해야 해요.")],lookup(port))
    assert result.record_lookup.status=="rejected" and not port.calls
    assert result.draft.conditions.fee_per_person==25000


def test_unbound_search_is_not_exposed_and_requested_search_is_rejected():
    assert len(agent_tool_schemas(search_enabled=False))==1
    assert len(agent_tool_schemas(search_enabled=True))==2
    result,_=run(request(),[AIMessage(content="",tool_calls=[search_call()]),AIMessage(content="조회가 연결되지 않았어요.")],None)
    assert result.record_lookup.status=="rejected"


def test_searches_share_the_existing_tool_limit():
    port=Port()
    result,_=run(request(),[AIMessage(content="",tool_calls=[search_call(f"s{i}") for i in range(4)]),
                           AIMessage(content="여기까지 확인했어요.")],lookup(port,Model()))
    assert result.limit_reached and len(port.calls)==3
    assert [e.result.status for e in result.executions]==["not_found"]*3+["rejected"]


@pytest.mark.parametrize("query",["", " ", "가"*4001])
def test_invalid_queries_fail_schema(query):
    with pytest.raises(ValidationError): SearchPastEventsInput(query=query)


def test_success_cannot_claim_evidence_without_result():
    with pytest.raises(ValidationError): RecordLookupResult(status="available",query="참가비")
