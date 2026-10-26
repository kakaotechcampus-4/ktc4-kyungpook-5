"""이전 조건 추출/검색/턴 조립 전용 타입."""
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator, model_validator
from ....contracts import ContractModel, NonBlankStr, RecordConflict, RecordFact
from ..schemas import (CalendarDate, PlanningConditions, ConditionField, MessageEvidence,
    ConditionValue, PlanningMessage)


class PlanningRecordSearchInput(ContractModel):
    """검색 의도가 정해진 뒤 사용하는 내부 입력. ID의 권한 검증은 BE 책임이다.

    planning_event_id는 현재 계획 식별용이고 target_event_id만 검색 필터다.
    기준 날짜는 호출자가 시간대를 고려해 제공한다. DB 저장·버전 검사는 하지 않는다.
    """

    club_id: NonBlankStr
    planning_event_id: NonBlankStr
    request_id: NonBlankStr
    base_version: Annotated[int, Field(strict=True, ge=0)]
    query: Annotated[NonBlankStr, Field(max_length=4000)]
    reference_date: CalendarDate
    conditions: PlanningConditions
    target_event_id: NonBlankStr | None = None


class PlanningRecordSearchResult(ContractModel):
    """검색 근거를 보존한 계획용 내부 결과. AVAILABLE은 완전한 답변을 뜻하지 않는다."""

    planning_event_id: NonBlankStr
    request_id: NonBlankStr
    base_version: Annotated[int, Field(strict=True, ge=0)]
    status: Literal["AVAILABLE", "NOT_FOUND"]
    cards: tuple[RecordFact, ...] = ()
    not_found: tuple[NonBlankStr, ...] = ()
    conflicts: tuple[RecordConflict, ...] = ()

    @model_validator(mode="after")
    def _require_consistent_status(self) -> Self:
        has_evidence = bool(self.cards or self.conflicts)
        if (self.status == "AVAILABLE") != has_evidence:
            raise ValueError("AVAILABLE은 카드 또는 충돌 근거가 있을 때만 사용합니다")
        if not has_evidence and not self.not_found:
            raise ValueError("근거가 없으면 확인하지 못한 내용을 남겨야 합니다")
        return self


class SetCondition(ContractModel):
    op: Literal["SET"]
    change: ConditionValue
    evidence: MessageEvidence
    # 짧은 수락은 이번 발화에 더해 원래 제안도 식별한다.
    offer_id: NonBlankStr | None
    context_evidence: tuple[MessageEvidence, ...]


class ClearCondition(ContractModel):
    op: Literal["CLEAR"]
    field: ConditionField
    evidence: MessageEvidence


ConditionOperation = SetCondition | ClearCondition


class UnresolvedCondition(ContractModel):
    field: ConditionField | None
    evidence: MessageEvidence
    reason: Literal["AMBIGUOUS_VALUE", "AMBIGUOUS_REFERENCE", "INCOMPLETE_DATE", "DEFERRED"]


class ConditionExtractionOutput(ContractModel):
    """모델이 생성하는 부분만 담는다. 요청 ID·버전·처리 상태는 코드가 붙인다."""

    operations: tuple[ConditionOperation, ...]
    unresolved: tuple[UnresolvedCondition, ...]


class PendingConditionOffer(ContractModel):
    id: NonBlankStr
    change: ConditionValue
    evidence: MessageEvidence


class ConditionExtractionInput(ContractModel):
    event_id: NonBlankStr
    request_id: NonBlankStr
    base_version: Annotated[int, Field(strict=True, ge=0)]
    conditions: PlanningConditions
    current_message: PlanningMessage
    context_messages: tuple[PlanningMessage, ...] = Field(default=(), max_length=20)
    reference_date: CalendarDate
    timezone: NonBlankStr
    pending_offer: PendingConditionOffer | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("유효한 IANA 시간대가 필요합니다") from error
        return value

    @model_validator(mode="after")
    def _validate_context(self) -> Self:
        if self.current_message.role != "user":
            raise ValueError("이번 발화는 사용자 메시지여야 합니다")
        messages = (*self.context_messages, self.current_message)
        if len({m.id for m in messages}) != len(messages):
            raise ValueError("메시지 ID는 중복될 수 없습니다")
        if sum(len(m.text) for m in messages) > 40000:
            raise ValueError("문맥은 총 40000자 이하여야 합니다")
        if self.pending_offer is not None:
            evidence = self.pending_offer.evidence
            source = next((m for m in self.context_messages if m.id == evidence.message_id), None)
            if source is None or source.role != "assistant" or evidence.quote not in source.text:
                raise ValueError("수락 대기 제안에는 문맥의 assistant 발화 근거가 필요합니다")
        return self


class ConditionExtractionResult(ContractModel):
    event_id: str
    request_id: str
    base_version: int
    status: Literal["APPLIED", "UNCHANGED", "NEEDS_CLARIFICATION", "VALIDATION_FAILED"]
    candidate_conditions: PlanningConditions
    applied_operations: tuple[ConditionOperation, ...]
    # 같은 값을 재확인한 SET/CLEAR도 미해결 수정을 해소할 수 있다.
    confirmed_fields: tuple[ConditionField, ...] = ()
    unresolved: tuple[UnresolvedCondition, ...]
    validation_errors: tuple[str, ...]
    prompt_version: str
    extraction_ms: int
