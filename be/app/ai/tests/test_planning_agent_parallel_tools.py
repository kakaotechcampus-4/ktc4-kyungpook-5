"""한 모델 응답에 Tool 요청이 여러 개 올 때 지켜야 할 동작을 고정한다(#265).

모델 응답은 정해진 값으로 대체하고 실제 graph·Tool 코드를 실행한다.
#265 표의 나머지 동작은 이미 다른 파일에서 고정하고 있다.
- 조건 변경 + 생성: test_planning_agent_generation.py
  test_direct_mixed_request_changes_conditions_then_generates_without_new_confirmation
- 거절된 조건 변경 + 생성: test_planning_agent_generation.py
  test_failed_date_change_blocks_generation_and_other_field_does_not_clear_it
- Tool 4개 이상: test_planning_agent_graph.py test_limit_disables_tools_and_prevents_extra_call_in_same_batch,
  test_planning_agent_generation.py test_generation_is_only_exposed_when_injected_and_shares_tool_limit
"""

import asyncio
from functools import partial

from langchain_core.messages import AIMessage

from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import OFFER_TOOL_NAME, TOOL_NAME
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.tests.test_plan_generation_graph import Model
from app.ai.tests.test_planning_agent_generation import call, change_call, gen_call, next_request, request
from app.ai.tests.test_planning_agent_records import Port, chunk, lookup, search_call


C2 = "예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마."


def defer_call(req, quote="계획 초안은 만들지 마", id="d1"):
    return call(OFFER_TOOL_NAME, dict(action="defer", reason="사용자가 아직 만들지 말자고 함",
        evidence=dict(message_id=req.current_message.id, quote=quote)), id)


def run(req, responses, *, model=None, search=None):
    seen = []
    model = model or Model()
    async def agent(messages, *, allow_tools):
        seen.append((messages, allow_tools))
        return responses[len(seen) - 1]
    result = asyncio.run(run_planning_agent_turn(req, invoke=agent, search=search,
        generate=partial(run_plan_generation, invoke=model)))
    return result, seen, model


def test_change_and_defer_in_one_response_keep_new_headcount_and_defer_on_it():
    # C2: "60명으로 바꾸고 초안은 만들지 마"를 한 응답에 담으면 모델 호출이 2번으로 끝나야 한다.
    req = request(C2)
    result, _, model = run(req, [AIMessage(content="", tool_calls=[change_call(req, "headcount", 60), defer_call(req)]),
                                 AIMessage(content="60명으로 바꿨고, 초안은 말씀하실 때 만들게요.")])
    assert result.model_calls == 2 and not model.calls
    assert [e.result.status for e in result.executions] == ["applied", "applied"]
    assert result.draft.conditions.headcount == 60
    # 보류 근거("만들지 마")로 질문 주제까지 보류하지 않는다. 처음 보류한 주제만 남는다.
    assert set(result.draft.deferred_topics) == set(req.draft.deferred_topics)
    # 앞 Tool이 바꾼 60명 기준으로 보류를 남겨야, 다음 턴에 같은 조건으로 다시 권하지 않는다.
    assert result.generation.offer.status == "deferred"
    assert result.generation.offer.basis_draft == result.draft

    req = next_request(result, text="장소는 어디가 좋을까?")
    again, _, _ = run(req, [AIMessage(content="", tool_calls=[call(OFFER_TOOL_NAME,
        dict(action="offer", reason="조건이 모였어요"), "t2")]), AIMessage(content="장소 후보를 먼저 볼게요.")])
    assert again.executions[0].result.status == "rejected"


def test_defer_before_change_in_one_response_is_rebased_on_new_conditions():
    # 모델이 [보류, 변경] 순서로 담아도 보류는 바뀐 60명 기준이어야 한다.
    req = request(C2)
    result, _, _ = run(req, [AIMessage(content="", tool_calls=[defer_call(req), change_call(req, "headcount", 60)]),
                             AIMessage(content="60명으로 바꿨고, 초안은 말씀하실 때 만들게요.")])
    assert result.draft.conditions.headcount == 60
    assert result.generation.offer.status == "deferred"
    assert result.generation.offer.basis_draft == result.draft


def test_change_does_not_rebase_defer_left_in_earlier_turn():
    # 이전 턴의 보류는 그때 조건 기준으로 남긴다. 조건이 바뀌면 다시 권할 수 있어야 한다.
    req = request(C2)
    first, _, _ = run(req, [AIMessage(content="", tool_calls=[defer_call(req)]), AIMessage(content="초안은 미룰게요.")])
    req = next_request(first, text="인원은 70명으로 하자")
    result, _, _ = run(req, [AIMessage(content="", tool_calls=[change_call(req, "headcount", 70)]),
                             AIMessage(content="70명으로 바꿨어요.")])
    assert result.generation.offer.basis_draft.conditions.headcount == 50


def test_two_generate_calls_in_one_response_run_generation_once():
    req = request("40명으로 바꾸고 바로 만들어줘")
    result, _, model = run(req, [AIMessage(content="", tool_calls=[change_call(req, "headcount", 40),
                                                                  gen_call(req, id="g1"), gen_call(req, id="g2")]),
                                 AIMessage(content="40명 기준으로 만들었어요.")])
    assert len(model.calls) == 1 and result.generation_model_calls == 1
    first, second = result.executions[1].result, result.executions[2].result
    assert first.status == second.status == "generated" and second.preview == first.preview
    assert result.generation.preview.basis_draft.conditions.headcount == 40


def test_change_after_search_in_same_response_waits_for_search_result():
    # "작년 금액으로 하자"를 한 응답에 담으면, 모델은 검색 결과를 보기 전에 금액을 정한 것이다.
    # 검색은 실행하되 그 뒤의 조건 변경은 실행하지 않고, 결과를 본 다음 호출에서 다시 요청하게 한다.
    req = request("작년 봄 MT 참가비로 하자", draft=request().draft.model_copy(update=dict(deferred_topics=())))
    guessed = change_call(req, "fee_per_person", 30000)
    result, seen, _ = run(req, [AIMessage(content="", tool_calls=[search_call(), guessed]),
                                AIMessage(content="작년 봄 MT 참가비는 45,000원이었어요. 이 금액으로 할까요?")],
                          search=lookup(Port((chunk("report", "참가비 45,000원"),))))
    assert result.record_lookup.status == "available"
    assert [e.name for e in result.executions] == ["search_past_events", TOOL_NAME]
    assert result.executions[1].result.status == "rejected"
    assert result.draft.conditions.fee_per_person == req.draft.conditions.fee_per_person
    assert "검색 결과" in seen[-1][0][-2].content
