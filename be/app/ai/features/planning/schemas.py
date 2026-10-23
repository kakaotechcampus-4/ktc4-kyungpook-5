"""계획 내부 타입. BE와 합의하기 전에는 app.ai 공개 계약으로 내보내지 않는다."""

from datetime import date, datetime
import re
from typing import Annotated, Self

from pydantic import BeforeValidator, Field, field_validator, model_validator

from app.ai.contracts import ContractModel
from app.core.enums import EventType


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
