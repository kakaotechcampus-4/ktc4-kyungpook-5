"""작은 생성 graph: 구조화 초안 작성 → 카탈로그·날짜·출처 검증."""

import json
import logging
from pathlib import Path
from typing import Protocol, TypedDict
from uuid import uuid4
from zoneinfo import ZoneInfo

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from ....errors import AIInvalidResponseError, AIOutputLimitError, AIRetryableError, AITimeoutError
from ....contracts import ExcludedPreviewStep
from .catalog import BY_CODE, CATALOG, PHASE_ORDER
from ....llm_stream import TextCallback
from .model import invoke_plan_composition
from .validation import PlanValidationError, PlanValidationViolation
from .schemas import (
    EventPlanPreview, PlanAssumption, PlanComposition, PlanGenerationInput,
    PlanGenerationResult, PreviewStep,
)


# v2(#276): 지시문은 v1과 같고, 모델에 보내는 출력 형식의 단계 코드가 카탈로그 13개로 줄었다.
# 모델이 받는 입력이 바뀌었으므로 측정 기록에서 v1 결과와 구분한다.
PROMPT_VERSION = "planning-generation-v2"
PROMPT = (Path(__file__).parent / "prompts/compose.md").read_text()
logger = logging.getLogger(__name__)


class CompositionInvoker(Protocol):
    # on_text는 진행 알림이 있을 때만 넘긴다. 그래서 받지 않는 기존 호출기도 그대로 쓸 수 있다.
    async def __call__(self, messages, schema: type[PlanComposition], *,
                       on_text: TextCallback | None = None) -> PlanComposition: ...


class GenerationGraphState(TypedDict):
    request: PlanGenerationInput
    composition: PlanComposition | None
    preview: EventPlanPreview | None


async def compose_plan(state: GenerationGraphState, *, invoke: CompositionInvoker,
                       on_text: TextCallback | None = None) -> dict:
    request = state["request"]
    # 출처 객체 대신 f1 같은 근거 번호를 공개한다. 출처는 검증 후 코드가 붙인다.
    context = dict(basis_draft=request.basis_draft.model_dump(mode="json"),
        messages=[m.model_dump(mode="json") for m in request.messages],
        reference_date=request.reference_date.isoformat(), timezone=request.timezone,
        catalog=[x.model_dump(mode="json") for x in CATALOG],
        reference_facts=[dict(id=f"f{i}", content=fact.content)
                         for i, fact in enumerate(request.reference_facts, 1)])
    streaming = {} if on_text is None else {"on_text": on_text}
    response = await invoke([SystemMessage(content=PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False))], PlanComposition, **streaming)
    try:
        composition = PlanComposition.model_validate(response)
    except ValidationError as error:
        raise AIInvalidResponseError("계획 초안의 출력 형식을 확인하지 못했어요.") from error
    return {"composition": composition}


def validate_plan(state: GenerationGraphState) -> dict:
    request, composition = state["request"], state["composition"]
    codes = [x.code for x in composition.steps]
    excluded = [x.code for x in composition.excluded_steps]
    def invalid(rule, path, expected, actual, **location):
        # 판정은 이 함수의 기존 분기에서만 한다. 원문 메시지 추측이나 검증 복제는 하지 않는다.
        raise PlanValidationError(PlanValidationViolation(
            rule=rule, path=path, expected=expected, actual=actual, **location))

    # 취소 단계·중복·설명 없이 사라진 단계를 차단한다. 제외 사유는 모델이 설명한다.
    if (len(set(codes)) != len(codes) or len(set(excluded)) != len(excluded)
            or set(codes) & set(excluded) or set(codes) | set(excluded) != set(BY_CODE)):
        invalid('catalog_partition', '', {'catalog_codes': sorted(BY_CODE), 'each_code_once': True},
                {'included': codes, 'excluded': excluded})
    phases = [PHASE_ORDER.index(BY_CODE[code].phase) for code in codes]
    if phases != sorted(phases):
        invalid('phase_order', '/steps', {'nondecreasing_phases': list(PHASE_ORDER)},
                {'step_codes': codes, 'phases': [BY_CODE[code].phase for code in codes]})

    zone = ZoneInfo(request.timezone)
    conditions = request.basis_draft.conditions
    def day(moment):
        return moment.astimezone(zone).date() if moment else None

    def date_text(value):
        return value.isoformat() if value is not None else None

    def moment_details(moment):
        return {'timestamp': date_text(moment), 'local_date': date_text(day(moment))}

    steps = []
    for step_index, step in enumerate(composition.steps):
        catalog = BY_CODE[step.code]
        start, end = day(step.starts_at), day(step.deadline)
        path = f'/steps/{step_index}'
        location = dict(step_code=step.code, timezone=request.timezone)
        if step.starts_at and step.deadline and step.deadline < step.starts_at:
            invalid('reversed_period', path + '/deadline',
                    {'on_or_after_timestamp': date_text(step.starts_at)}, moment_details(step.deadline), **location)
        if conditions.start_date is None and (start or end or any(a.due_date for a in step.actions)):
            if start or end:
                field, moment = ('starts_at', step.starts_at) if start else ('deadline', step.deadline)
                invalid('dates_when_unknown', path + '/' + field, None, moment_details(moment), **location)
            index = next(i for i, action in enumerate(step.actions) if action.due_date)
            invalid('dates_when_unknown', f'{path}/actions/{index}/due_date', None,
                    date_text(step.actions[index].due_date), action_index=index, **location)
        if any(a.type not in catalog.actions for a in step.actions):
            index = next(i for i, action in enumerate(step.actions) if action.type not in catalog.actions)
            invalid('action_type', f'{path}/actions/{index}/type', list(catalog.actions),
                    step.actions[index].type, action_index=index, **location)
        for action_index, action in enumerate(step.actions):
            if action.due_date and ((start and action.due_date < start) or (end and action.due_date > end)):
                invalid('action_due_outside_step', f'{path}/actions/{action_index}/due_date',
                        {'earliest_local_date': date_text(start), 'latest_local_date': date_text(end), 'inclusive': True},
                        date_text(action.due_date), action_index=action_index, **location)
        if conditions.start_date:
            if catalog.phase in PHASE_ORDER[:2] or step.code == "PRE_EVENT_NOTICE":
                if any(d and d > conditions.start_date for d in (start, end)):
                    field, moment = (('starts_at', step.starts_at) if start and start > conditions.start_date
                                     else ('deadline', step.deadline))
                    invalid('before_event_after_start', path + '/' + field,
                            {'on_or_before_local_date': date_text(conditions.start_date)}, moment_details(moment), **location)
            if step.code == "EVENT_DAY":
                if start and start != conditions.start_date:
                    invalid('event_start_mismatch', path + '/starts_at', date_text(conditions.start_date),
                            moment_details(step.starts_at), **location)
                if end and end != conditions.end_date:
                    invalid('event_end_mismatch', path + '/deadline', date_text(conditions.end_date),
                            moment_details(step.deadline), **location)
            if step.code in {"SETTLE_EXPENSES", "REFUND_FEES", "RECORD_FEEDBACK"} and conditions.end_date:
                if any(d and d < conditions.end_date for d in (start, end)):
                    field, moment = (('starts_at', step.starts_at) if start and start < conditions.end_date
                                     else ('deadline', step.deadline))
                    invalid('after_event_before_end', path + '/' + field,
                            {'on_or_after_local_date': date_text(conditions.end_date)}, moment_details(moment), **location)
        steps.append(PreviewStep(**step.model_dump(), name=catalog.name, phase=catalog.phase, actor=catalog.actor))

    facts = {f"f{i}": fact for i, fact in enumerate(request.reference_facts, 1)}
    assumptions = []
    for assumption_index, assumption in enumerate(composition.assumptions):
        if any(id not in facts for id in assumption.fact_ids):
            index = next(i for i, id in enumerate(assumption.fact_ids) if id not in facts)
            invalid('unknown_fact_id', f'/assumptions/{assumption_index}/fact_ids/{index}',
                    sorted(facts), assumption.fact_ids[index])
        sources = []
        for id in assumption.fact_ids:
            for source in facts[id].sources:
                if source not in sources:
                    sources.append(source)
        assumptions.append(PlanAssumption(content=assumption.content, sources=tuple(sources)))
    questions = list(composition.open_questions)
    if conditions.start_date is None and "행사 날짜" not in questions:
        questions.append("행사 날짜")
    # LLM은 code/reason만 쓴다. 검증된 제외 목록에 고정 이름을 붙여 화면 결과를 만든다.
    excluded_steps = tuple(ExcludedPreviewStep(
        code=item.code, name=BY_CODE[item.code].name, reason=item.reason,
    ) for item in composition.excluded_steps)
    return {"preview": EventPlanPreview(id=str(uuid4()), basis_draft=request.basis_draft.model_copy(deep=True),
        trigger=request.trigger, steps=tuple(steps), excluded_steps=excluded_steps,
        assumptions=tuple(assumptions), open_questions=tuple(questions), warnings=composition.warnings)}


async def run_plan_generation(request: PlanGenerationInput, *, invoke: CompositionInvoker = invoke_plan_composition,
                              on_text: TextCallback | None = None) -> PlanGenerationResult:
    """원본 조건을 바꾸지 않고 검증된 초안만 반환한다. 저장·외부 실행은 없다.

    on_text: 모델이 보낸 계획 JSON 글자 조각을 받은 순서대로 받는다(#388, #389). 진행 알림용이며 검증 전 글이다.
    """
    if request.basis_draft.conditions.event_type is None:
        return PlanGenerationResult(status="needs_clarification", reason="어떤 행사인지 먼저 정해 주세요.")
    graph = StateGraph(GenerationGraphState)
    stage = "compose_plan"
    async def compose(state):
        return await compose_plan(state, invoke=invoke, on_text=on_text)
    def validate(state):
        nonlocal stage
        stage = "validate_plan"
        return validate_plan(state)
    graph.add_node("compose_plan", compose)
    graph.add_node("validate_plan", validate)
    graph.add_edge(START, "compose_plan")
    graph.add_edge("compose_plan", "validate_plan")
    graph.add_edge("validate_plan", END)
    try:
        result = await graph.compile().ainvoke(dict(request=request.model_copy(deep=True), composition=None, preview=None))
    except AIRetryableError as error:
        # 단계·분류만 남긴다. 공급자 오류 원문/traceback/사용자 대화는 로깅하지 않는다.
        if isinstance(error, AIOutputLimitError):
            code, reason = "output_limit", "모델 응답이 출력 한도에서 끊겨 초안을 완성하지 못했어요."
        elif isinstance(error, AITimeoutError):
            code, reason = "timeout", "계획 생성 응답을 기다리는 시간이 초과됐어요. 다시 시도해 주세요."
        elif isinstance(error, AIInvalidResponseError):
            code = "invalid_plan" if stage == "validate_plan" else "invalid_output"
            reason = ("생성된 초안이 단계·날짜·근거 검증을 통과하지 못했어요. 다시 시도해 주세요."
                      if stage == "validate_plan" else "모델의 초안 출력 형식을 읽지 못했어요. 다시 시도해 주세요.")
        else:
            code, reason = "temporarily_unavailable", "계획 생성 모델에 일시적으로 연결하지 못했어요. 다시 시도해 주세요."
        logger.warning("plan_generation_failed stage=%s code=%s", stage, code)
        return PlanGenerationResult(status="failed", reason=reason, model_calls=1)
    return PlanGenerationResult(status="generated", preview=result["preview"], model_calls=1)
