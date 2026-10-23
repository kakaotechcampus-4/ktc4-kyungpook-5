"""계획 내부 타입. BE와 합의하기 전에는 app.ai 공개 계약으로 내보내지 않는다."""

from datetime import date, datetime
import re
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BeforeValidator, Field, field_validator, model_validator

from app.ai.contracts import ContractModel, NonBlankStr
from app.core.enums import EventType
from ..retrieval.schemas import RecordConflict, RecordFact


def _require_calendar_date(value: object) -> object:
    """timestamp/datetime의 날짜 변환과 불완전한 날짜의 묵시적 보정을 막는다."""
    if isinstance(value, datetime):
        raise ValueError("시각이 아닌 날짜를 입력해야 합니다")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("날짜는 date 또는 YYYY-MM-DD 형식이어야 합니다")


CalendarDate = Annotated[date, BeforeValidator(_require_calendar_date)]
Headcount = Annotated[int, Field(strict=True, ge=1)]
Won = Annotated[int, Field(strict=True, ge=0)]


class PlanningConditions(ContractModel):
    """사용자가 정한 행사 조건의 불변 스냅샷. None은 미정, 0원은 무료다.

    과거 기록·AI 제안·복수 후보는 이 객체에 자동 병합하지 않는다.
    이 타입은 값의 형식만 검증하며 사용자 수락 여부는 추출 단계가 판단한다.
    BE 저장 모델이 아니므로 title 미정을 허용한다.
    """

    title: str | None = Field(default=None, max_length=100)
    event_type: EventType | None = None
    headcount: Headcount | None = None
    fee_per_person: Won | None = None
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    location: str | None = Field(default=None, max_length=200)
    # 명시한 예산 상한만 보관한다. 참가비나 합계를 계산하지 않는다.
    budget_total: Won | None = None

    @field_validator("title", "location")
    @classmethod
    def _require_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("미정은 null로 표현하고 공백만 입력할 수 없습니다")
        return value

    @model_validator(mode="after")
    def _require_ordered_dates(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다")
        return self


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


ConditionField = Literal[
    "title", "event_type", "headcount", "fee_per_person", "start_date",
    "end_date", "location", "budget_total",
]


class TitleValue(ContractModel):
    field: Literal["title"]
    value: Annotated[NonBlankStr, Field(max_length=100)]


class LocationValue(ContractModel):
    field: Literal["location"]
    value: Annotated[NonBlankStr, Field(max_length=200)]


class EventTypeValue(ContractModel):
    field: Literal["event_type"]
    value: EventType


class HeadcountValue(ContractModel):
    field: Literal["headcount"]
    value: Headcount


class MoneyValue(ContractModel):
    field: Literal["fee_per_person", "budget_total"]
    value: Won


class DateValue(ContractModel):
    field: Literal["start_date", "end_date"]
    value: CalendarDate


# 게이트웨이는 oneOf를 거부한다. 일반 Union은 anyOf를 만들며 각 Literal이
# 필드별 분기를 검증하므로 잘못된 필드/값 조합을 허용하지 않는다.
ConditionValue = TitleValue | LocationValue | EventTypeValue | HeadcountValue | MoneyValue | DateValue


class MessageEvidence(ContractModel):
    message_id: NonBlankStr
    quote: NonBlankStr


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


class PlanningMessage(ContractModel):
    id: NonBlankStr
    role: Literal["user", "assistant"]
    text: Annotated[NonBlankStr, Field(max_length=4000)]


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
