"""agent는 다음 행동을 고르고, tools는 실제 변경을 검증·실행한다."""

import json
from pathlib import Path
from typing import Protocol

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

from ....errors import AIInvalidResponseError
from ....llm import ainvoke_with_tools
from .schemas import PlanningAgentState, PlanningAgentTurnInput, ToolExecution
from .record_tool import RecordLookupResult, RecordSearcher, SearchPastEventsInput
from .tools import ConditionUpdateResult, UpdateEventConditionsInput, update_event_conditions


PROMPT_VERSION = "planning-agent-v2"
MAX_TOOL_CALLS = 3
PROMPT = (Path(__file__).parent / "prompts/chat.md").read_text()
TOOL_NAME = "update_event_conditions"
SEARCH_TOOL_NAME = "search_past_events"


def condition_tool_schema() -> dict:
    """LLM에는 변경 인자만 공개한다. 현재 초안과 사용자 메시지는 코드가 주입한다."""
    schema = convert_to_openai_tool(UpdateEventConditionsInput)
    schema["function"].update(name=TOOL_NAME, description=(
        "사용자가 제시·수정·해제·수락한 행사 조건을 변경하거나 질문 주제를 보류/재개한다. "
        "여러 조건은 한 호출로 묶는다. 단순 상담·가정 질문에는 사용하지 않는다. "
        "SET에는 값, tentative(잠정)/specified(명시), 이번 사용자 메시지 ID와 실제 문구를 넣는다. "
        "CLEAR는 미정으로 되돌린다. 보류/재개에도 이번 발화 근거가 필요하다. 날짜 주제는 dates다."
    ))
    return schema


class AgentInvoker(Protocol):
    async def __call__(self, messages: list[AnyMessage], *, allow_tools: bool) -> AIMessage: ...


def agent_tool_schemas(*, search_enabled: bool) -> list[dict]:
    tools = [condition_tool_schema()]
    if search_enabled:
        schema = convert_to_openai_tool(SearchPastEventsInput)
        schema["function"].update(name=SEARCH_TOOL_NAME, description=(
            "동아리의 과거 행사 기록에서 질문의 근거를 찾는다. "
            "연도·계절·행사와 무엇을 알고 싶은지 query에 명확히 적는다. "
            "현재 행사 조건을 변경하지 않는다. 결과는 과거 사실·실제 출처·미확인·자료 차이를 포함한다."
        ))
        tools.append(schema)
    return tools


async def call_agent_model(messages: list[AnyMessage], *, allow_tools: bool,
                           search_enabled: bool = False) -> AIMessage:
    return await ainvoke_with_tools(messages, tools=agent_tool_schemas(search_enabled=search_enabled),
                                   allow_tools=allow_tools)


async def agent_node(
    state: PlanningAgentState, *, request: PlanningAgentTurnInput, invoke: AgentInvoker,
    search_available: bool = False,
) -> dict:
    # “그렇게 하자”는 messages에서, 현재 금액은 최신 draft에서 확인한다.
    context = dict(current_message_id=request.current_message.id,
                   reference_date=request.reference_date.isoformat(), timezone=request.timezone,
                   draft=state["draft"].model_dump(mode="json"), search_available=search_available)
    allow_tools = state["tool_calls"] < MAX_TOOL_CALLS
    instruction = PROMPT + "\n\n현재 실행 문맥(JSON 데이터):\n" + json.dumps(context, ensure_ascii=False)
    if not allow_tools:
        instruction += "\n이번 턴의 Tool 한도에 도달했습니다. 추가 실행 없이 실제 완료한 결과와 남은 내용을 답하세요."
    response = await invoke([SystemMessage(content=instruction), *state["messages"]], allow_tools=allow_tools)
    if not isinstance(response, AIMessage) or response.invalid_tool_calls:
        raise AIInvalidResponseError("모델의 Tool 요청을 읽을 수 없습니다")
    if not allow_tools and response.tool_calls:
        raise AIInvalidResponseError("Tool 사용이 끝난 뒤에도 모델이 Tool을 요청했습니다")
    if response.tool_calls:
        ids = [call["id"] for call in response.tool_calls]
        used = {call["id"] for m in state["messages"] if isinstance(m, AIMessage) for call in m.tool_calls}
        if any(not item or item in used for item in ids) or len(ids) != len(set(ids)):
            raise AIInvalidResponseError("Tool 호출 ID가 비어 있거나 중복됐습니다")
    elif not response.text.strip():
        raise AIInvalidResponseError("모델이 답변을 반환하지 않았습니다")
    return {"messages": [response], "model_calls": state["model_calls"] + 1}


async def tools_node(state: PlanningAgentState, *, request: PlanningAgentTurnInput,
                     search: RecordSearcher | None = None) -> dict:
    draft = state["draft"]
    executions = list(state["executions"])
    messages = []
    count = state["tool_calls"]
    limited = state["limit_reached"]
    lookup = state["record_lookup"]
    def reject(call, reason):
        if call["name"] == SEARCH_TOOL_NAME:
            query = call["args"].get("query")
            return RecordLookupResult(status="rejected", query=query if isinstance(query, str) else None, reason=reason)
        return ConditionUpdateResult(status="rejected", draft=draft, reason=reason)
    # 모델이 여러 호출을 내더라도 앞 Tool의 결과를 다음 Tool의 입력 상태로 사용한다.
    for call in state["messages"][-1].tool_calls:
        if count >= MAX_TOOL_CALLS:
            limited = True
            result = reject(call, "이번 턴의 Tool 실행 한도에 도달했어요.")
        else:
            count += 1
            if call["name"] == SEARCH_TOOL_NAME:
                if search is None:
                    result = reject(call, "기록 검색이 연결되지 않았어요.")
                else:
                    try:
                        arguments = SearchPastEventsInput.model_validate(call["args"])
                    except ValidationError:
                        result = reject(call, "검색 질문 query만 전달해 주세요. 질문은 비어 있지 않은 4000자 이하의 글이어야 해요.")
                    else:
                        # 기존 검색 결과만 돌려받는다. 검색 Tool에는 현재 초안을 바꿀 권한이 없다.
                        result = await search(arguments, draft, request.reference_date)
            elif call["name"] != TOOL_NAME:
                result = reject(call, "지원하지 않는 Tool이에요.")
            else:
                try:
                    arguments = UpdateEventConditionsInput.model_validate(call["args"])
                except ValidationError as error:
                    # 원본 오류 전체 대신 필드 위치·이유만 보여줘 LLM이 다음 호출을 고칠 수 있게 한다.
                    issues = [{"field": ".".join(map(str, e["loc"])), "reason": e["msg"]}
                              for e in error.errors(include_input=False, include_url=False)]
                    result = ConditionUpdateResult(status="rejected", draft=draft,
                        reason="Tool 인자 형식을 확인해 주세요: " + json.dumps(issues, ensure_ascii=False))
                else:
                    result = update_event_conditions(draft, arguments, current_message=request.current_message)
        if isinstance(result, ConditionUpdateResult):
            draft = result.draft
        else:
            lookup = result
        executions.append(ToolExecution(tool_call_id=call["id"], name=call["name"], result=result))
        # 호출 ID와 연결한 결과를 LLM에 전달한다. '반영했어요' 문장을 코드가 만들지 않는다.
        messages.append(ToolMessage(content=result.model_dump_json(), tool_call_id=call["id"], name=call["name"]))
    return dict(messages=messages, draft=draft, executions=executions, tool_calls=count,
                limit_reached=limited or count >= MAX_TOOL_CALLS, record_lookup=lookup)
