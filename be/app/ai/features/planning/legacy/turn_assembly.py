"""검증된 중간 결과를 답변·표시 질문·다음 턴 상태로 조립한다. 모델 호출은 없다."""

from .questions import DATE_FIELDS, PlanningQuestion, select_next_question
from .schemas import MessageEvidence, SetCondition, UnresolvedCondition
from .turn_flow import PlanningTurnPreparation
from .turn_policy import assess_generation_readiness
from .turn_schemas import PendingClarification, PlanningTurnInput, PlanningTurnResult

LABELS = {"title": "행사 이름", "event_type": "행사 유형", "headcount": "인원",
          "fee_per_person": "1인 참가비", "budget_total": "예산 상한", "location": "장소",
          "start_date": "시작일", "end_date": "종료일"}


def _topic(field):
    return set(DATE_FIELDS) if field in DATE_FIELDS else {field}


def merge_pending(request: PlanningTurnInput, prepared: PlanningTurnPreparation):
    """필드별 최신 미해결을 보존한다. 날짜는 하나의 주제로 정리한다."""
    extraction = prepared.extraction
    pending = {p.item.field: p for p in request.pending_clarifications}
    # “40명으로”가 기존 값과 같아도 명확한 답이다. 실제 값 변경 여부와 별개로 메모를 푼다.
    resolved = set()
    for field in extraction.confirmed_fields:
        resolved.update(_topic(field))
    for op in extraction.applied_operations:
        resolved.update(_topic(op.change.field if isinstance(op, SetCondition) else op.field))
    for item in extraction.unresolved:
        if item.reason == "DEFERRED":
            fields = _topic(item.field) if item.field is not None else set(request.question_state.last_question_fields)
            resolved.update(fields)
    pending = {field: p for field, p in pending.items() if field not in resolved}
    # 기존 메모 중 해결된 대상만 제거하고, 이번에 새로 모호해진 대상은 최신 근거로 교체한다.
    for item in extraction.unresolved:
        if item.reason != "DEFERRED":
            pending[item.field] = PendingClarification(
                id=f"{extraction.request_id}:{item.field or 'unknown'}", item=item,
            )
    if extraction.status == "VALIDATION_FAILED":
        # 날짜 변경을 거절한 사실이 다음 턴에 잊히지 않도록 날짜 주제의 메모를 남긴다.
        pending["start_date"] = PendingClarification(
            id=f"{extraction.request_id}:start_date",
            item=UnresolvedCondition(field="start_date", reason="AMBIGUOUS_VALUE",
                evidence=MessageEvidence(message_id=request.extraction_input.current_message.id,
                                         quote=request.extraction_input.current_message.text)),
        )
    return tuple(pending.values())


def _format_value(field, value):
    if field == "headcount":
        return f"{value}명"
    if field in {"fee_per_person", "budget_total"}:
        return f"{value:,}원"
    return str(value)


def assemble_planning_reply(prepared: PlanningTurnPreparation) -> list[str]:
    """확인된 변경·검색 결과만 설명한다. 최종 질문은 조립 함수가 뒤에 붙인다."""
    extraction = prepared.extraction
    parts = []
    if extraction.status == "VALIDATION_FAILED":
        parts.append("요청하신 조건은 충돌이 있어 반영하지 않았어요.")
    for op in extraction.applied_operations:
        field = op.change.field if isinstance(op, SetCondition) else op.field
        parts.append(f"{LABELS[field]}: {_format_value(field, op.change.value)}으로 반영했어요."
                     if isinstance(op, SetCondition) else f"{LABELS[field]}: 미정으로 바꿨어요.")
    lookup = prepared.record_lookup
    if lookup.status == "FAILED":
        parts.append("과거 기록은 검색에 실패해 확인하지 못했어요.")
    elif lookup.status == "SUCCEEDED":
        result = lookup.result
        for card in result.cards:
            sources = "; ".join(f"{s.file_name} · {s.location.label}" for s in card.sources)
            parts.append(f"참고 기록: {card.content} (출처: {sources})")
        for conflict in result.conflicts:
            parts.append(f"기록 간 차이가 있어요: {conflict.description}")
            for value in conflict.values:
                sources = "; ".join(f"{s.file_name} · {s.location.label}" for s in value.sources)
                parts.append(f"{value.content} (출처: {sources})")
        if result.not_found:
            parts.append("이번 검색에서 확인하지 못한 내용: " + ", ".join(result.not_found))
    return parts


def assemble_planning_turn(request: PlanningTurnInput, prepared: PlanningTurnPreparation) -> PlanningTurnResult:
    source = request.extraction_input
    extraction = prepared.extraction
    if (source.event_id, source.request_id, source.base_version) != (
        extraction.event_id, extraction.request_id, extraction.base_version,
    ):
        raise ValueError("다른 요청의 중간 결과를 조립할 수 없습니다")
    pending = merge_pending(request, prepared)
    # 이전 미해결은 질문에 활용하되 이번 추출 결과 자체를 덮어쓰지는 않는다.
    effective = extraction.model_copy(update={"unresolved": tuple(p.item for p in pending) +
        tuple(i for i in extraction.unresolved if i.reason == "DEFERRED")})
    candidate = select_next_question(effective, request.question_state,
                                    allow_missing=prepared.lookup_decision.action == "SKIP",
                                    record_question=False)
    question = candidate.question
    # 조회 대상 확인이 우선이면 조건 질문 후보를 교체한다. 질문 이력은 아래에서 확정한다.
    if extraction.status != "VALIDATION_FAILED" and prepared.record_lookup.status == "NEEDS_CLARIFICATION":
        question = PlanningQuestion(fields=(), reason="CLARIFY", text=prepared.record_lookup.clarification)
    state = candidate.state
    # 화면에 실제 표시하는 질문만 '물어본 항목'으로 기록한다. 숨긴 후보는 소비하지 않는다.
    state = state.model_copy(update={
        "asked_fields": tuple(sorted(set(state.asked_fields) | set(question.fields if question else ()))),
        "last_question_fields": question.fields if question else (),
    })
    parts = assemble_planning_reply(prepared)
    # 같은 collected를 설명하는 변경 안내·검색 안내 뒤에 최종 질문을 한 번만 붙인다.
    if question:
        parts.append(question.text)
    if not parts:
        parts.append("현재 조건을 유지했어요.")
    return PlanningTurnResult(
        event_id=source.event_id, request_id=source.request_id, base_version=source.base_version,
        extraction=extraction, collected=extraction.candidate_conditions,
        reply="\n".join(parts), question=question, next_question_state=state,
        pending_clarifications=pending, record_lookup=prepared.record_lookup,
        readiness=assess_generation_readiness(extraction.candidate_conditions,
            has_pending_modification=bool(pending), has_condition_conflict=extraction.status == "VALIDATION_FAILED"),
    )
