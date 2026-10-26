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
from .catalog import BY_CODE, CATALOG, PHASE_ORDER
from .model import invoke_plan_composition
from .schemas import (
    EventPlanPreview, PlanAssumption, PlanComposition, PlanGenerationInput,
    PlanGenerationResult, PreviewStep,
)


PROMPT_VERSION = "planning-generation-v1"
PROMPT = (Path(__file__).parent / "prompts/compose.md").read_text()
logger = logging.getLogger(__name__)


class CompositionInvoker(Protocol):
    async def __call__(self, messages, schema: type[PlanComposition]) -> PlanComposition: ...


class GenerationGraphState(TypedDict):
    request: PlanGenerationInput
    composition: PlanComposition | None
    preview: EventPlanPreview | None


async def compose_plan(state: GenerationGraphState, *, invoke: CompositionInvoker) -> dict:
    request = state["request"]
    # 출처 객체 대신 f1 같은 근거 번호를 공개한다. 출처는 검증 후 코드가 붙인다.
    context = dict(basis_draft=request.basis_draft.model_dump(mode="json"),
        messages=[m.model_dump(mode="json") for m in request.messages],
        reference_date=request.reference_date.isoformat(), timezone=request.timezone,
        catalog=[x.model_dump(mode="json") for x in CATALOG],
        reference_facts=[dict(id=f"f{i}", content=fact.content)
                         for i, fact in enumerate(request.reference_facts, 1)])
    response = await invoke([SystemMessage(content=PROMPT),
        HumanMessage(content=json.dumps(context, ensure_ascii=False))], PlanComposition)
    try:
        composition = PlanComposition.model_validate(response)
    except ValidationError as error:
        raise AIInvalidResponseError("계획 초안의 출력 형식을 확인하지 못했어요.") from error
    return {"composition": composition}


def validate_plan(state: GenerationGraphState) -> dict:
    request, composition = state["request"], state["composition"]
    codes = [x.code for x in composition.steps]
    excluded = [x.code for x in composition.excluded_steps]
    def invalid(reason: str):
        raise AIInvalidResponseError(reason)

    # 취소 단계·중복·설명 없이 사라진 단계를 차단한다. 제외 사유는 모델이 설명한다.
    if (len(set(codes)) != len(codes) or len(set(excluded)) != len(excluded)
            or set(codes) & set(excluded) or set(codes) | set(excluded) != set(BY_CODE)):
        invalid("계획의 포함·제외 단계가 카탈로그와 맞지 않아요.")
    phases = [PHASE_ORDER.index(BY_CODE[code].phase) for code in codes]
    if phases != sorted(phases):
        invalid("계획의 세 묶음 순서가 맞지 않아요.")

    zone = ZoneInfo(request.timezone)
    conditions = request.basis_draft.conditions
    def day(moment):
        return moment.astimezone(zone).date() if moment else None

    steps = []
    for step in composition.steps:
        catalog = BY_CODE[step.code]
        start, end = day(step.starts_at), day(step.deadline)
        if step.starts_at and step.deadline and step.deadline < step.starts_at:
            invalid("단계 마감이 시작보다 빨라요.")
        if conditions.start_date is None and (start or end or any(a.due_date for a in step.actions)):
            invalid("행사 날짜가 미정이면 단계 날짜와 기한도 미정으로 남겨야 해요.")
        if any(a.type not in catalog.actions for a in step.actions):
            invalid("단계에서 허용하지 않은 예정 행동이 있어요.")
        for action in step.actions:
            if action.due_date and ((start and action.due_date < start) or (end and action.due_date > end)):
                invalid("예정 행동의 기한이 단계 기간 밖에 있어요.")
        if conditions.start_date:
            if catalog.phase in PHASE_ORDER[:2] or step.code == "PRE_EVENT_NOTICE":
                if any(d and d > conditions.start_date for d in (start, end)):
                    invalid("행사 전에 할 단계가 행사 시작 뒤로 잡혔어요.")
            if step.code == "EVENT_DAY":
                if start and start != conditions.start_date:
                    invalid("행사 당일 단계의 시작일이 현재 조건과 달라요.")
                if end and end != conditions.end_date:
                    invalid("행사 당일 단계의 종료일이 현재 조건과 달라요.")
            if step.code in {"SETTLE_EXPENSES", "REFUND_FEES", "RECORD_FEEDBACK"} and conditions.end_date:
                if any(d and d < conditions.end_date for d in (start, end)):
                    invalid("행사 뒤에 할 단계가 종료 전으로 잡혔어요.")
        steps.append(PreviewStep(**step.model_dump(), name=catalog.name, phase=catalog.phase, actor=catalog.actor))

    facts = {f"f{i}": fact for i, fact in enumerate(request.reference_facts, 1)}
    assumptions = []
    for assumption in composition.assumptions:
        if any(id not in facts for id in assumption.fact_ids):
            invalid("제공하지 않은 기록 근거가 계획에 포함됐어요.")
        sources = []
        for id in assumption.fact_ids:
            for source in facts[id].sources:
                if source not in sources:
                    sources.append(source)
        assumptions.append(PlanAssumption(content=assumption.content, sources=tuple(sources)))
    questions = list(composition.open_questions)
    if conditions.start_date is None and "행사 날짜" not in questions:
        questions.append("행사 날짜")
    return {"preview": EventPlanPreview(id=str(uuid4()), basis_draft=request.basis_draft.model_copy(deep=True),
        trigger=request.trigger, steps=tuple(steps), excluded_steps=composition.excluded_steps,
        assumptions=tuple(assumptions), open_questions=tuple(questions), warnings=composition.warnings)}


async def run_plan_generation(request: PlanGenerationInput, *, invoke: CompositionInvoker = invoke_plan_composition) -> PlanGenerationResult:
    """원본 조건을 바꾸지 않고 검증된 초안만 반환한다. 저장·외부 실행은 없다."""
    if request.basis_draft.conditions.event_type is None:
        return PlanGenerationResult(status="needs_clarification", reason="어떤 행사인지 먼저 정해 주세요.")
    graph = StateGraph(GenerationGraphState)
    stage = "compose_plan"
    async def compose(state):
        return await compose_plan(state, invoke=invoke)
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
