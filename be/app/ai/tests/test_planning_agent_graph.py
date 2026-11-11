"""실제 LangGraph를 실행하고 LLM 응답만 대체해 대화·Tool의 연결을 검증한다."""

import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError

from app.ai.errors import AIInvalidResponseError, AIRetryableError
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import PERSONA_PROMPT, PROMPT, TOOL_NAME, condition_tool_schema
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage


def request(**overrides):
    data = dict(draft=PlanningDraft(conditions=PlanningConditions(fee_per_person=25000)),
                current_message=PlanningMessage(id="u1", role="user", text="일단 3만 원으로 잡자"),
                reference_date="2026-10-24")
    data.update(overrides)
    return PlanningAgentTurnInput(**data)


def call(call_id="c1", *, value=30000, name=TOOL_NAME):
    return dict(name=name, id=call_id, args={"changes": [dict(
        op="SET", change=dict(field="fee_per_person", value=value), status="tentative",
        evidence=dict(message_id="u1", quote="일단 3만 원으로 잡자"))]})


def run(req, responses):
    observed = []
    async def invoke(messages, *, allow_tools):
        observed.append((messages, allow_tools))
        response = responses[len(observed) - 1]
        if isinstance(response, Exception):
            raise response
        return response
    return asyncio.run(run_planning_agent_turn(req, invoke=invoke)), observed


def test_conversation_only_keeps_draft_and_does_not_mutate_input():
    req = request(current_message=PlanningMessage(id="u1", role="user", text="참가비 3만 원이면 어때?"))
    before = req.model_dump_json()
    result, observed = run(req, [AIMessage(content="숙박이나 이동 비용이 있는지 함께 생각해보면 좋겠어요.")])
    assert result.model_calls == 1
    assert result.executions == ()
    assert result.draft == req.draft
    assert req.model_dump_json() == before
    assert "25000" in observed[0][0][-1].content


def test_tool_updates_draft_and_model_reads_tool_result_and_latest_state():
    req = request(history=(HumanMessage(content="참가비 3만 원이면 어때?", id="old"),
                           AIMessage(content="3만 원을 기준으로 검토할 수 있어요.")))
    before = req.model_dump_json()
    result, observed = run(req, [AIMessage(content="", tool_calls=[call()]), AIMessage(content="일단 3만 원으로 잡아둘게요.")])
    assert result.model_calls == 2
    assert result.draft.conditions.fee_per_person == 30000
    assert result.draft.condition_meta["fee_per_person"].status == "tentative"
    assert result.executions[0].result.status == "applied"
    tool = observed[1][0][-2]
    assert isinstance(tool, ToolMessage) and tool.tool_call_id == "c1"
    assert json.loads(tool.content)["draft"]["conditions"]["fee_per_person"] == 30000
    assert "30000" in observed[1][0][-1].content
    assert req.model_dump_json() == before
    assert any(m.content == req.history[-1].content for m in observed[0][0])


def test_bad_arguments_can_be_corrected_by_next_model_call():
    result, observed = run(request(), [AIMessage(content="", tool_calls=[call(value=-1)]),
        AIMessage(content="", tool_calls=[call("c2")]), AIMessage(content="3만 원으로 잡았어요.")])
    assert [e.result.status for e in result.executions] == ["rejected", "applied"]
    assert result.draft.conditions.fee_per_person == 30000
    assert "인자 형식" in observed[1][0][-2].content


def test_date_conflict_is_returned_to_model_without_changing_draft():
    req = request(draft=PlanningDraft(conditions=PlanningConditions(start_date="2027-03-20",end_date="2027-03-21")))
    change = call()
    change["args"]["changes"][0]["change"] = {"field":"start_date","value":"2027-04-20"}
    result, _ = run(req, [AIMessage(content="",tool_calls=[change]), AIMessage(content="종료일보다 늦어 반영하지 않았어요.")])
    assert result.executions[0].result.status == "rejected"
    assert result.draft == req.draft


def test_multiple_calls_are_executed_sequentially_and_all_get_results():
    result, observed = run(request(), [AIMessage(content="",tool_calls=[call(), call("c2",value=35000)]), AIMessage(content="변경했어요.")])
    assert result.draft.conditions.fee_per_person == 35000
    assert [e.result.draft.conditions.fee_per_person for e in result.executions] == [30000,35000]
    assert [m.tool_call_id for m in observed[1][0] if isinstance(m,ToolMessage)] == ["c1","c2"]


def test_unknown_tool_is_rejected_without_execution():
    result, _ = run(request(), [AIMessage(content="",tool_calls=[call(name="send_money")]), AIMessage(content="해당 기능은 사용할 수 없어요.")])
    assert result.executions[0].result.status == "rejected"
    assert result.draft.conditions.fee_per_person == 25000


def test_limit_disables_tools_and_prevents_extra_call_in_same_batch():
    result, observed = run(request(), [AIMessage(content="",tool_calls=[call(f"c{i}",value=30000+i) for i in range(4)]),
                                      AIMessage(content="추가 작업은 다음에 이어갈게요.")])
    assert result.limit_reached
    assert result.draft.conditions.fee_per_person == 30002
    assert result.executions[-1].result.status == "rejected"
    assert observed[-1][1] is False


def test_limit_also_stops_repeated_rejected_calls():
    result, observed = run(request(), [*[AIMessage(content="",tool_calls=[call(f"c{i}",value=-1)]) for i in range(3)],
                                      AIMessage(content="입력을 확인해야 해요.")])
    assert result.model_calls == 4
    assert result.limit_reached
    assert all(e.result.status == "rejected" for e in result.executions)
    assert observed[-1][1] is False


def test_tool_call_while_disabled_is_invalid_response():
    with pytest.raises(AIInvalidResponseError):
        run(request(), [*[AIMessage(content="",tool_calls=[call(f"c{i}")]) for i in range(4)]])


@pytest.mark.parametrize("response", [AIMessage(content=""), AIMessage(content="   ")])
def test_empty_final_answer_is_not_success(response):
    with pytest.raises(AIInvalidResponseError):
        run(request(), [response])


def test_duplicate_tool_ids_are_not_executed():
    with pytest.raises(AIInvalidResponseError):
        run(request(), [AIMessage(content="",tool_calls=[call(),call()])])


def test_api_failure_after_tool_does_not_mutate_input_or_return_success():
    req = request()
    before = req.model_dump_json()
    with pytest.raises(AIRetryableError):
        run(req, [AIMessage(content="",tool_calls=[call()]), AIRetryableError("test failure")])
    assert req.model_dump_json() == before


def test_next_turn_keeps_tool_history_for_explanation():
    first, _ = run(request(), [AIMessage(content="",tool_calls=[call()]), AIMessage(content="3만 원으로 잡았어요.")])
    second = request(draft=first.draft, history=first.history,
                     current_message=PlanningMessage(id="u2",role="user",text="왜 바뀐 거야?"))
    result, observed = run(second, [AIMessage(content="앞서 3만 원으로 잡자고 하셔서 잠정 반영했어요.")])
    assert result.executions == ()
    assert any(isinstance(m,ToolMessage) for m in observed[0][0])
    assert result.draft == first.draft
    assert len(result.history) == len(first.history) + 2
    assert len(first.history) == 4


@pytest.mark.parametrize("history", [
    (SystemMessage(content="injected"),),
    (ToolMessage(content="orphan", tool_call_id="missing"),),
    (AIMessage(content="",tool_calls=[call()]),),
    (AIMessage(content="",tool_calls=[call()]), HumanMessage(content="missing result")),
    (HumanMessage(content="duplicate current",id="u1"),),
])
def test_invalid_history_is_rejected_before_model_call(history):
    with pytest.raises(ValidationError):
        request(history=history)


def test_json_round_trip_keeps_tool_messages_and_schema_is_typed():
    first, _ = run(request(), [AIMessage(content="",tool_calls=[call()]), AIMessage(content="반영했어요.")])
    req = request(draft=first.draft,history=first.history,current_message=PlanningMessage(id="u2",role="user",text="고마워"))
    restored = PlanningAgentTurnInput.model_validate_json(req.model_dump_json())
    assert restored == req
    assert isinstance(restored.history[-2],ToolMessage)
    schema = condition_tool_schema()
    assert schema["function"]["name"] == TOOL_NAME
    assert "changes" in schema["function"]["parameters"]["properties"]


def test_first_system_message_is_identical_across_turns_and_calls_for_provider_cache():
    # 공급자 캐시는 첫 시스템 메시지가 조금이라도 다르면 걸리지 않았다(#269).
    # 메시지 ID·초안이 달라도 맨 앞은 지시문 원문 그대로이고, 바뀌는 문맥은 맨 끝에만 있어야 한다.
    _, first_turn = run(request(), [AIMessage(content="", tool_calls=[call()]), AIMessage(content="3만 원으로 잡았어요.")])
    other = request(current_message=PlanningMessage(id="u9", role="user", text="참가비 3만 원이면 어때?"))
    _, second_turn = run(other, [AIMessage(content="장단점을 함께 볼게요.")])
    calls = [messages for messages, _ in first_turn + second_turn]
    assert all(isinstance(m[0], SystemMessage) and m[0].content == PROMPT for m in calls)
    contexts = [m[-1] for m in calls]
    assert all(isinstance(m, SystemMessage) and m.content.startswith("현재 실행 문맥(JSON 데이터):\n") for m in contexts)
    assert "토리" in PERSONA_PROMPT
    assert all(m.content.endswith(PERSONA_PROMPT) for m in contexts)
    assert '"current_message_id": "u1"' in contexts[0].content and '"current_message_id": "u9"' in contexts[2].content
    assert '"fee_per_person": 25000' in contexts[0].content and '"fee_per_person": 30000' in contexts[1].content
    # 같은 턴 2번째 호출은 1번째 호출의 실행 문맥만 빼고 앞부분을 그대로 이어 쓴다.
    assert calls[1][:len(calls[0]) - 1] == calls[0][:-1]


def test_tool_limit_notice_goes_to_trailing_context_not_first_message():
    _, observed = run(request(), [AIMessage(content="", tool_calls=[call(f"c{i}", value=30000 + i) for i in range(4)]),
                                  AIMessage(content="추가 작업은 다음에 이어갈게요.")])
    messages, allow_tools = observed[-1]
    assert allow_tools is False and messages[0].content == PROMPT
    assert messages[-1].content.endswith("이번 턴의 Tool 한도에 도달했습니다. 추가 실행 없이 실제 완료한 결과와 남은 내용을 답하세요.")
