"""현재 Agent와 legacy가 공유하는 조건 값/발화 타입. 공개 조건은 루트에서 재사용한다."""

from typing import Annotated, Literal
from pydantic import Field
from app.core.enums import EventType
from ...contracts import (ContractModel, NonBlankStr, CalendarDate, Headcount, Won,
    PlanningConditions, ConditionField, MessageEvidence)


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


class PlanningMessage(ContractModel):
    id: NonBlankStr
    role: Literal["user", "assistant"]
    text: Annotated[NonBlankStr, Field(max_length=4000)]
