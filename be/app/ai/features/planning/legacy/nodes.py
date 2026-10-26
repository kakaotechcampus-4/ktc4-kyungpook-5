"""이번 발화의 변경을 추출하고 원본과 분리된 조건 후보를 만든다."""

import time
from collections.abc import Awaitable, Callable
from functools import cache
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from ....errors import AIInvalidResponseError
from ....llm import ainvoke_structured
from .schemas import (
    ConditionExtractionInput, ConditionExtractionOutput, ConditionExtractionResult,
    PlanningConditions, SetCondition,
)

PROMPT_VERSION = "planning-conditions-v1"
Extractor = Callable[[list[BaseMessage]], Awaitable[ConditionExtractionOutput]]


@cache
def _system_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "extract_conditions.md").read_text(encoding="utf-8")


def build_extraction_messages(request: ConditionExtractionInput) -> list[BaseMessage]:
    # 과거 대화도 HumanMessage의 JSON 데이터로 전달한다. system 지시로 승격하지 않는다.
    payload = request.model_dump_json(exclude={"event_id", "request_id", "base_version"})
    return [SystemMessage(_system_prompt()), HumanMessage(payload)]


async def call_extraction_model(messages: list[BaseMessage]) -> ConditionExtractionOutput:
    return await ainvoke_structured(messages, ConditionExtractionOutput)


def validate_and_apply(
    request: ConditionExtractionInput,
    output: ConditionExtractionOutput,
    *,
    extraction_ms: int = 0,
) -> ConditionExtractionResult:
    """근거/중복은 모델 오류, 날짜 충돌은 사용자에게 확인할 검증 결과로 구분한다."""
    current = request.current_message
    context = {m.id: m.text for m in request.context_messages}

    def check_current(evidence):
        if evidence.message_id != current.id or evidence.quote not in current.text:
            raise AIInvalidResponseError("조건 변경의 근거가 이번 발화와 맞지 않습니다")

    values = request.conditions.model_dump()
    seen = set()
    for operation in output.operations:
        check_current(operation.evidence)
        field = operation.change.field if isinstance(operation, SetCondition) else operation.field
        if field in seen:
            raise AIInvalidResponseError("같은 조건에 변경이 중복되었습니다")
        seen.add(field)
        if isinstance(operation, SetCondition):
            for evidence in operation.context_evidence:
                if evidence.message_id not in context or evidence.quote not in context[evidence.message_id]:
                    raise AIInvalidResponseError("참고한 대화 근거가 입력 문맥에 없습니다")
            if operation.offer_id is not None:
                offer = request.pending_offer
                if offer is None or offer.id != operation.offer_id or offer.change != operation.change:
                    raise AIInvalidResponseError("수락한 제안의 값과 변경 값이 다릅니다")
                if offer.evidence not in operation.context_evidence:
                    raise AIInvalidResponseError("수락한 제안의 발화 근거가 빠졌습니다")
            values[field] = operation.change.value
        else:
            values[field] = None

    for unresolved in output.unresolved:
        check_current(unresolved.evidence)
        if unresolved.field in seen:
            raise AIInvalidResponseError("같은 조건을 변경하면서 미해결로 남길 수 없습니다")

    common = dict(
        event_id=request.event_id, request_id=request.request_id,
        base_version=request.base_version, unresolved=output.unresolved,
        prompt_version=PROMPT_VERSION, extraction_ms=extraction_ms,
    )
    try:
        candidate = PlanningConditions.model_validate(values)
    except ValidationError:
        # operation 타입은 이미 검증됐다. 최종 날짜 관계가 잘못되면 턴 전체를 보존한다.
        return ConditionExtractionResult(
            **common, status="VALIDATION_FAILED", candidate_conditions=request.conditions,
            applied_operations=(), validation_errors=("END_BEFORE_START",),
        )
    changed = tuple(
        op for op in output.operations
        if getattr(request.conditions, op.change.field if isinstance(op, SetCondition) else op.field)
        != getattr(candidate, op.change.field if isinstance(op, SetCondition) else op.field)
    )
    status = "NEEDS_CLARIFICATION" if output.unresolved else "APPLIED" if changed else "UNCHANGED"
    return ConditionExtractionResult(
        **common, status=status, candidate_conditions=candidate,
        applied_operations=changed, validation_errors=(),
        confirmed_fields=tuple(op.change.field if isinstance(op, SetCondition) else op.field for op in output.operations),
    )

# 현재 조건, 대화를 LLM에 전달, SET,CLEAR 목록을 받는다.
async def extract_condition_changes(
    request: ConditionExtractionInput, *, extract: Extractor = call_extraction_model,
) -> ConditionExtractionResult:
    """LangGraph에 연결할 추출 단계. DB 저장·검색·질문 생성은 하지 않는다."""
    started = time.perf_counter()
    output = await extract(build_extraction_messages(request))
    # 테스트 주입/다른 어댑터에서도 잘못된 응답을 정상 변경 없음으로 바꾸지 않는다.
    if not isinstance(output, ConditionExtractionOutput):
        raise AIInvalidResponseError("조건 추출 응답 형식이 올바르지 않습니다")
    return validate_and_apply(
        request, output, extraction_ms=round((time.perf_counter() - started) * 1000),
    )
