"""검증된 조건 결과에서 한 주제만 질문한다. 모델 호출과 DB 저장은 하지 않는다."""

from typing import Annotated, Literal

from pydantic import Field

from ...contracts import ContractModel, NonBlankStr
from .schemas import ConditionExtractionResult, ConditionField, SetCondition

QUESTION_POLICY_VERSION = "planning-questions-v1"
DATE_FIELDS: tuple[ConditionField, ...] = ("start_date", "end_date")
FIELD_ORDER: tuple[ConditionField, ...] = (
    "event_type", "start_date", "end_date", "headcount", "location", "title", "fee_per_person",
)


class PlanningQuestionState(ContractModel):
    event_id: NonBlankStr
    asked_fields: tuple[ConditionField, ...] = ()
    deferred_fields: tuple[ConditionField, ...] = ()
    last_question_fields: tuple[ConditionField, ...] = ()


class PlanningQuestion(ContractModel):
    fields: tuple[ConditionField, ...]
    reason: Literal["CONFLICT", "CLARIFY", "MISSING"]
    text: NonBlankStr
    quick_replies: Annotated[tuple[NonBlankStr, ...], Field(max_length=4)] = ("아직 모르겠어요",)
    allow_free_text: Literal[True] = True


class PlanningQuestionResult(ContractModel):
    event_id: str
    request_id: str
    base_version: int
    question: PlanningQuestion | None
    state: PlanningQuestionState
    policy_version: str = QUESTION_POLICY_VERSION


def _topic(field: ConditionField) -> tuple[ConditionField, ...]:
    return DATE_FIELDS if field in DATE_FIELDS else (field,)


def _question_text(field: ConditionField | None, *, changing: bool) -> str:
    if field is None:
        return "어떤 조건을 어떻게 바꾸고 싶은지 구체적으로 알려 주실래요?"
    if field in DATE_FIELDS:
        return "행사 시작일과 종료일을 언제로 정할까요? 하루 행사라면 같은 날짜를 알려 주세요."
    if field == "headcount":
        return "예상 인원을 몇 명으로 바꿀까요?" if changing else "예상 참가 인원은 몇 명인가요?"
    return {
        "event_type": "어떤 종류의 행사를 준비하시나요?",
        "location": "행사 장소를 어디로 정할까요?",
        "title": "행사 이름을 무엇으로 정할까요?",
        "fee_per_person": "1인 참가비를 얼마로 정할까요? 무료 행사라면 0원으로 알려 주세요.",
        "budget_total": "예산 상한을 얼마로 정할까요?",
    }[field]


def select_next_question(
    extraction: ConditionExtractionResult, state: PlanningQuestionState,
    *, allow_missing: bool = True, record_question: bool = True,
) -> PlanningQuestionResult:
    """질문 상태는 반환만 한다. 응답과 함께 저장할 책임은 호출자에게 있다."""
    if extraction.event_id != state.event_id:
        raise ValueError("다른 행사의 질문 상태를 사용할 수 없습니다")
    asked, deferred = set(state.asked_fields), set(state.deferred_fields)
    conditions = extraction.candidate_conditions
    for op in extraction.applied_operations:
        field = op.change.field if isinstance(op, SetCondition) else op.field
        deferred.difference_update(_topic(field))
        if not isinstance(op, SetCondition):
            asked.difference_update(_topic(field))

    for item in extraction.unresolved:
        if item.reason == "DEFERRED":
            fields = _topic(item.field) if item.field is not None else state.last_question_fields
            deferred.update(fields)

    question = None
    if extraction.status == "VALIDATION_FAILED":
        if extraction.validation_errors != ("END_BEFORE_START",):
            raise ValueError("지원하지 않는 조건 검증 오류입니다")
        question = PlanningQuestion(
            fields=DATE_FIELDS, reason="CONFLICT",
            text="요청하신 일정은 종료일이 시작일보다 빨라 반영하지 않았어요. 시작일과 종료일을 다시 알려 주실래요?",
        )
    else:
        for item in extraction.unresolved:
            if item.reason == "DEFERRED":
                continue
            fields = _topic(item.field) if item.field is not None else ()
            deferred.difference_update(fields)
            question = PlanningQuestion(
                fields=fields, reason="CLARIFY",
                text=_question_text(item.field, changing=item.field is not None and getattr(conditions, item.field) is not None),
            )
            break
        if question is None and allow_missing:
            for field in FIELD_ORDER:
                fields = _topic(field)
                if getattr(conditions, field) is not None or (set(fields) & (asked | deferred)):
                    continue
                text = _question_text(field, changing=False)
                if field in DATE_FIELDS:
                    if conditions.start_date is not None:
                        text = f"시작일은 {conditions.start_date.isoformat()}로 정해져 있어요. 종료일은 언제인가요?"
                    elif conditions.end_date is not None:
                        text = f"종료일은 {conditions.end_date.isoformat()}로 정해져 있어요. 시작일은 언제인가요?"
                question = PlanningQuestion(fields=fields, reason="MISSING", text=text)
                break

    if question is not None and record_question:
        asked.update(question.fields)
    return PlanningQuestionResult(
        event_id=extraction.event_id, request_id=extraction.request_id, base_version=extraction.base_version,
        question=question,
        state=PlanningQuestionState(
            event_id=state.event_id, asked_fields=tuple(sorted(asked)), deferred_fields=tuple(sorted(deferred)),
            last_question_fields=question.fields if question and record_question else (),
        ),
    )
