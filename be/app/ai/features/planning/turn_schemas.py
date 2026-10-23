"""한 턴 조립용 내부 계약. 공개 facade 연결·상태 전이는 5-2/5-3에서 구현한다."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ...contracts import ContractModel, NonBlankStr
from .questions import PlanningQuestion, PlanningQuestionState
from .schemas import (
    ConditionExtractionInput, ConditionExtractionResult, PlanningConditions,
    PlanningRecordSearchResult, UnresolvedCondition,
)
from .turn_policy import GenerationReadiness, assess_generation_readiness


class PendingClarification(ContractModel):
    id: NonBlankStr
    item: UnresolvedCondition

    @model_validator(mode="after")
    def _active_only(self):
        if self.item.reason == "DEFERRED" or len(self.item.evidence.quote) > 4000:
            raise ValueError("미해결 수정에는 보류 항목 또는 4000자 초과 근거를 넣을 수 없습니다")
        return self


PendingItems = Annotated[tuple[PendingClarification, ...], Field(max_length=9)]


def _unique_pending(items):
    if len({i.id for i in items}) != len(items) or len({i.item.field for i in items}) != len(items):
        raise ValueError("미해결 항목의 ID와 대상은 각각 중복될 수 없습니다")


class PlanningTurnInput(ContractModel):
    club_id: NonBlankStr
    extraction_input: ConditionExtractionInput
    question_state: PlanningQuestionState
    pending_clarifications: PendingItems = ()

    @model_validator(mode="after")
    def _same_event(self):
        if self.extraction_input.event_id != self.question_state.event_id:
            raise ValueError("다른 행사의 질문 상태를 사용할 수 없습니다")
        _unique_pending(self.pending_clarifications)
        return self


class RecordLookupState(ContractModel):
    status: Literal["SKIPPED", "NEEDS_CLARIFICATION", "SUCCEEDED", "FAILED"]
    result: PlanningRecordSearchResult | None = None
    clarification: NonBlankStr | None = None
    error_code: Literal["TIMEOUT", "RETRYABLE", "INVALID_RESPONSE"] | None = None

    @model_validator(mode="after")
    def _payload_matches_status(self):
        actual = (self.result is not None, self.clarification is not None, self.error_code is not None)
        expected = {
            "SKIPPED": (False, False, False), "SUCCEEDED": (True, False, False),
            "NEEDS_CLARIFICATION": (False, True, False), "FAILED": (False, False, True),
        }
        if actual != expected[self.status]:
            raise ValueError("검색 상태와 결과·질문·오류 정보가 일치해야 합니다")
        return self


class PlanningTurnResult(ContractModel):
    event_id: NonBlankStr
    request_id: NonBlankStr
    base_version: Annotated[int, Field(strict=True, ge=0)]
    extraction: ConditionExtractionResult
    collected: PlanningConditions
    reply: NonBlankStr
    question: PlanningQuestion | None = None
    next_question_state: PlanningQuestionState
    pending_clarifications: PendingItems = ()
    record_lookup: RecordLookupState
    readiness: GenerationReadiness

    @model_validator(mode="after")
    def _consistent_turn(self):
        identity = (self.event_id, self.request_id, self.base_version)
        if identity != (self.extraction.event_id, self.extraction.request_id, self.extraction.base_version):
            raise ValueError("조건 추출 결과의 행사·요청·버전이 일치해야 합니다")
        if self.collected != self.extraction.candidate_conditions:
            raise ValueError("표시 조건은 검증된 후보와 같아야 합니다")
        if self.next_question_state.event_id != self.event_id:
            raise ValueError("다른 행사의 질문 상태입니다")
        if self.record_lookup.result is not None:
            found = self.record_lookup.result
            if identity != (found.planning_event_id, found.request_id, found.base_version):
                raise ValueError("검색 결과의 행사·요청·버전이 일치해야 합니다")
        fields = self.question.fields if self.question else ()
        if self.next_question_state.last_question_fields != fields:
            raise ValueError("표시 질문과 마지막 질문 상태가 일치해야 합니다")
        if self.question and (self.reply.count(self.question.text) != 1 or
                              not set(fields).issubset(self.next_question_state.asked_fields)):
            raise ValueError("질문은 답변에 한 번 포함하고 질문 이력에 반영해야 합니다")
        _unique_pending(self.pending_clarifications)
        for item in self.extraction.unresolved:
            if item.reason != "DEFERRED" and not any(p.item == item for p in self.pending_clarifications):
                raise ValueError("이번 턴의 미해결 수정은 다음 턴 상태에도 보존해야 합니다")
        expected = assess_generation_readiness(
            self.collected, has_pending_modification=bool(self.pending_clarifications) or
            any(i.reason != "DEFERRED" for i in self.extraction.unresolved),
            has_condition_conflict=self.extraction.status == "VALIDATION_FAILED",
        )
        if self.readiness != expected:
            raise ValueError("초안 생성 가능 판단이 조건·미해결 상태와 일치해야 합니다")
        return self
