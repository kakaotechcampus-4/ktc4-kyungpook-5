"""두 Node의 연결과 내부 한 턴 실행 진입점."""

from functools import partial

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from .nodes import MAX_TOOL_CALLS, PROMPT_VERSION, AgentInvoker, agent_node, call_agent_model, tools_node
from .schemas import PlanningAgentState, PlanningAgentTurnInput, PlanningAgentTurnResult
from .record_tool import RecordSearcher
from ..generation.schemas import PlanGenerator
from ..generation.offers import same_basis


def build_planning_graph(request: PlanningAgentTurnInput, *, invoke: AgentInvoker | None = None,
                         search: RecordSearcher | None = None, generate: PlanGenerator | None = None):
    invoke = invoke or partial(call_agent_model, search_enabled=search is not None, generation_enabled=generate is not None)
    graph = StateGraph(PlanningAgentState)
    graph.add_node("agent", partial(agent_node, request=request, invoke=invoke, search_available=search is not None,
                                    generation_available=generate is not None))
    graph.add_node("tools", partial(tools_node, request=request, search=search, generate=generate))
    graph.add_edge(START, "agent")
    # 자연어 답변이면 종료하고, Tool 요청이면 실행 결과를 다시 읽는다.
    graph.add_conditional_edges("agent", lambda state: "tools" if state["messages"][-1].tool_calls else END)
    graph.add_edge("tools", "agent")
    return graph.compile()


async def run_planning_agent_turn(
    request: PlanningAgentTurnInput, *, invoke: AgentInvoker | None = None,
    search: RecordSearcher | None = None,
    generate: PlanGenerator | None = None,
) -> PlanningAgentTurnResult:
    """체크포인트·DB 없이 호출자가 전달한 상태로 한 턴을 실행한다."""
    # LangGraph가 메시지 ID를 보완해도 입력 이력·초안은 바뀌지 않도록 복사한다.
    state = PlanningAgentState(
        messages=[*[m.model_copy(deep=True) for m in request.history],
                  HumanMessage(content=request.current_message.text, id=request.current_message.id)],
        draft=request.draft.model_copy(deep=True), executions=[], tool_calls=0, model_calls=0, limit_reached=False,
        record_lookup=None,
        generation=request.generation.model_copy(deep=True), generation_result=None, generation_model_calls=0,
    )
    result = await build_planning_graph(request, invoke=invoke, search=search, generate=generate).ainvoke(
        state, {"recursion_limit": 2 * MAX_TOOL_CALLS + 5},
    )
    return PlanningAgentTurnResult(
        reply=result["messages"][-1].text, draft=result["draft"], history=tuple(result["messages"]),
        executions=tuple(result["executions"]), model_calls=result["model_calls"],
        limit_reached=result["limit_reached"], prompt_version=PROMPT_VERSION, record_lookup=result["record_lookup"],
        generation=result["generation"], generation_result=result["generation_result"],
        generation_model_calls=result["generation_model_calls"],
        preview_is_current=bool(result["generation"].preview and
            same_basis(result["generation"].preview.basis_draft, result["draft"]) and
            not result["generation"].condition_change_pending),
    )
