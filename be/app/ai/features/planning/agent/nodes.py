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
from ..generation.offers import OfferUpdateResult, UpdateGenerationOfferInput, same_basis, update_generation_offer
from ..generation.schemas import PlanGenerationResult, PlanGenerator, PlanningGenerationState
from .generation_tools import GenerateEventPlanInput, condition_generation_state, generate_event_plan


PROMPT_VERSION = "planning-agent-v8"
MAX_TOOL_CALLS = 3
# 한 응답에 Tool 요청 여러 개를 허용한다. "60명으로 바꾸고 초안은 만들지 마"의 변경과 보류를
# 한 번에 받아 모델 호출 1번을 줄인다. 실행은 tools_node가 앞에서부터 차례로 한다(#265).
PARALLEL_TOOL_CALLS = True
PROMPT = (Path(__file__).parent / "prompts/chat.md").read_text()
TOOL_NAME = "update_event_conditions"
SEARCH_TOOL_NAME = "search_past_events"
OFFER_TOOL_NAME = "update_generation_offer"
GENERATE_TOOL_NAME = "generate_event_plan"


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


def agent_tool_schemas(*, search_enabled: bool, generation_enabled: bool = False) -> list[dict]:
    tools = [condition_tool_schema()]
    if search_enabled:
        schema = convert_to_openai_tool(SearchPastEventsInput)
        schema["function"].update(name=SEARCH_TOOL_NAME, description=(
            "동아리의 과거 행사 기록에서 질문의 근거를 찾는다. "
            "연도·계절·행사와 무엇을 알고 싶은지 query에 명확히 적는다. "
            "현재 행사 조건을 변경하지 않는다. 결과는 과거 사실·실제 출처·미확인·자료 차이를 포함한다."
        ))
        tools.append(schema)
    if generation_enabled:
        for model, name, description in (
            (UpdateGenerationOfferInput, OFFER_TOOL_NAME,
             "계획 초안 생성을 권할 때 offer로 권유 상태를 남기고, 사용자가 미루면 defer로 보류한다. "
             "이 Tool은 생성하지 않는다. 같은 조건으로 반복 권유하지 말고 질문·상담에 먼저 답한다."),
            (GenerateEventPlanInput, GENERATE_TOOL_NAME,
             "사용자가 계획 초안을 직접 요청하거나 생성 권유를 수락했을 때만 사용한다. quote에 이번 발화의 원문을 넣는다. 메시지 ID와 조건은 코드가 주입한다. "
             "권유 수락은 현재 offer_id를 넣고, 직접 생성 요청은 생략한다. 모호한 수락이면 먼저 질문한다. "
             "거절된 조건 변경 대신 현재 남은 조건을 쓰겠다고 사용자가 명시한 경우에만 use_current_conditions=true다."),
        ):
            schema = convert_to_openai_tool(model)
            schema["function"].update(name=name, description=description)
            tools.append(schema)
    return tools


async def call_agent_model(messages: list[AnyMessage], *, allow_tools: bool,
                           search_enabled: bool = False, generation_enabled: bool = False) -> AIMessage:
    return await ainvoke_with_tools(messages, tools=agent_tool_schemas(search_enabled=search_enabled,
                                                                    generation_enabled=generation_enabled),
                                   allow_tools=allow_tools, parallel_tool_calls=PARALLEL_TOOL_CALLS)


TOOL_LIMIT_NOTICE = "이번 턴의 Tool 한도에 도달했습니다. 추가 실행 없이 실제 완료한 결과와 남은 내용을 답하세요."


def agent_messages(context: dict, messages: list[AnyMessage], *, allow_tools: bool) -> list[AnyMessage]:
    """대화 모델에 보낼 메시지 순서를 정한다.

    공급자 입력 캐시는 첫 시스템 메시지가 글자 하나라도 다르면 걸리지 않았다(#269).
    그래서 맨 앞에는 바뀌지 않는 지시문만 두고, 메시지 ID·초안처럼 매 호출 바뀌는 문맥은 맨 끝에 둔다.
    예: [지시문] [이력] [이번 발화] [Tool 결과…] [실행 문맥] → 실행 문맥 앞부분은 다음 호출에서 재사용된다.
    """
    execution = "현재 실행 문맥(JSON 데이터):\n" + json.dumps(context, ensure_ascii=False)
    if not allow_tools:
        execution += "\n" + TOOL_LIMIT_NOTICE
    return [SystemMessage(content=PROMPT), *messages, SystemMessage(content=execution)]


async def agent_node(
    state: PlanningAgentState, *, request: PlanningAgentTurnInput, invoke: AgentInvoker,
    search_available: bool = False,
    generation_available: bool = False,
) -> dict:
    # “그렇게 하자”는 messages에서, 현재 금액은 최신 draft에서 확인한다.
    context = dict(current_message_id=request.current_message.id,
                   reference_date=request.reference_date.isoformat(), timezone=request.timezone,
                   draft=state["draft"].model_dump(mode="json"), search_available=search_available,
                   generation_available=generation_available, generation=state["generation"].model_dump(mode="json"),
                   preview_is_current=bool(state["generation"].preview and
                       same_basis(state["generation"].preview.basis_draft, state["draft"]) and
                       not state["generation"].condition_change_pending))
    allow_tools = state["tool_calls"] < MAX_TOOL_CALLS
    response = await invoke(agent_messages(context, state["messages"], allow_tools=allow_tools),
                            allow_tools=allow_tools)
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
                     search: RecordSearcher | None = None, generate: PlanGenerator | None = None) -> dict:
    draft = state["draft"]
    executions = list(state["executions"])
    messages = []
    count = state["tool_calls"]
    limited = state["limit_reached"]
    lookup = state["record_lookup"]
    generation = state["generation"]
    generation_result = state["generation_result"]
    generation_calls = state["generation_model_calls"]
    # 같은 응답 안의 앞선 Tool을 기억한다. 모델은 응답 하나를 다 쓴 뒤에야 Tool 결과를 받는다.
    searched = False  # 앞에 검색이 있었다 → 뒤의 조건 변경은 검색 결과를 보기 전에 정한 값이다.
    deferred_offer_id = None  # 이번 응답에서 남긴 보류 → 뒤의 조건 변경 뒤 기준으로 맞춘다.
    def reject(call, reason):
        if call["name"] == SEARCH_TOOL_NAME:
            query = call["args"].get("query")
            return RecordLookupResult(status="rejected", query=query if isinstance(query, str) else None, reason=reason)
        if call["name"] == OFFER_TOOL_NAME:
            return OfferUpdateResult(status="rejected", offer=generation.offer, reason=reason)
        if call["name"] == GENERATE_TOOL_NAME:
            return PlanGenerationResult(status="needs_clarification", reason=reason)
        return ConditionUpdateResult(status="rejected", draft=draft, reason=reason)
    # 모델이 여러 호출을 내더라도 앞 Tool의 결과를 다음 Tool의 입력 상태로 사용한다.
    for call in state["messages"][-1].tool_calls:
        if count >= MAX_TOOL_CALLS:
            limited = True
            result = reject(call, "이번 턴의 Tool 실행 한도에 도달했어요.")
        else:
            count += 1
            if call["name"] in {OFFER_TOOL_NAME, GENERATE_TOOL_NAME}:
                if generate is None:
                    result = reject(call, "계획 생성이 연결되지 않았어요.")
                else:
                    try:
                        model = UpdateGenerationOfferInput if call["name"] == OFFER_TOOL_NAME else GenerateEventPlanInput
                        arguments = model.model_validate(call["args"])
                    except ValidationError:
                        result = reject(call, "생성 Tool의 인자와 이번 사용자 발화 근거를 확인해 주세요.")
                    else:
                        if call["name"] == OFFER_TOOL_NAME:
                            result = update_generation_offer(draft, generation, arguments, current_message=request.current_message)
                        else:
                            update = await generate_event_plan(arguments, request=request, draft=draft, state=generation,
                                messages=[*state["messages"], *messages], generate=generate)
                            generation, result = update.generation, update.result
            elif call["name"] == SEARCH_TOOL_NAME:
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
            elif searched:
                # 예: "작년 참가비로 하자" → [검색, 참가비 변경]을 한 응답에 담으면 금액은 모델의 짐작이다.
                # 검색 결과를 본 다음 호출에서 다시 요청하게 한다. 사용자가 값을 직접 말한 변경은
                # 보통 검색보다 앞에 오고, 그 순서는 그대로 실행한다.
                result = reject(call, "같은 응답의 검색 결과를 보기 전에 정한 값이라 반영하지 않았어요. "
                                      "검색 결과를 확인한 뒤 필요하면 다시 요청해 주세요.")
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
            if call["name"] == TOOL_NAME:
                generation = condition_generation_state(generation, result, call["args"])
                offer = generation.offer
                if result.status == "applied" and offer and offer.id == deferred_offer_id:
                    # "60명으로 바꿔줘, 초안은 만들지 마"를 [보류, 변경] 순서로 담아도
                    # 보류를 60명 기준으로 남긴다. 50명 기준이면 다음 턴에 같은 권유를 다시 하게 된다.
                    generation = generation.model_copy(update=dict(
                        offer=offer.model_copy(update=dict(basis_draft=draft.model_copy(deep=True)))))
        elif isinstance(result, RecordLookupResult):
            lookup = result
        elif isinstance(result, OfferUpdateResult):
            generation = PlanningGenerationState(offer=result.offer, preview=generation.preview,
                condition_change_pending=generation.condition_change_pending,
                pending_condition_fields=generation.pending_condition_fields)
            if result.status == "applied" and result.offer.status == "deferred":
                deferred_offer_id = result.offer.id
        else:
            generation_result = result
            generation_calls += result.model_calls
        searched = searched or call["name"] == SEARCH_TOOL_NAME
        executions.append(ToolExecution(tool_call_id=call["id"], name=call["name"], result=result))
        # 호출 ID와 연결한 결과를 LLM에 전달한다. '반영했어요' 문장을 코드가 만들지 않는다.
        messages.append(ToolMessage(content=result.model_dump_json(), tool_call_id=call["id"], name=call["name"]))
    return dict(messages=messages, draft=draft, executions=executions, tool_calls=count,
                limit_reached=limited or count >= MAX_TOOL_CALLS, record_lookup=lookup,
                generation=generation, generation_result=generation_result, generation_model_calls=generation_calls)
