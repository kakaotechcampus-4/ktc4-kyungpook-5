"""후보 확인·확정 항목·예약 응답의 작은 계약."""

from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import CamelModel, ServiceMemberRole, UtcDateTime


class ConfirmedFields(CamelModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["TASK", "SCHEDULE"]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    assignee_name: str | None = Field(default=None, max_length=100)
    assignee_account_id: str | None = Field(default=None, min_length=1, max_length=26)
    due_at: AwareDatetime | None = None
    scheduled_at: AwareDatetime | None = None
    timezone: str = Field(default="Asia/Seoul", max_length=64)
    reminder_at: AwareDatetime
    recipient_account_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("제목을 입력해 주세요.")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Asia/Seoul 같은 IANA 시간대를 입력해 주세요.") from exc
        return value

    @field_validator("due_at", "scheduled_at", "reminder_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @field_validator("recipient_account_ids")
    @classmethod
    def unique_recipients(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 26 for item in value):
            raise ValueError("수신자의 accountId를 확인해 주세요.")
        return sorted(set(value))

    @model_validator(mode="after")
    def exact_item_time(self) -> "ConfirmedFields":
        if self.kind == "TASK" and (self.due_at is None or self.scheduled_at is not None):
            raise ValueError("할 일에는 dueAt을 입력하고 scheduledAt은 비워 주세요.")
        if self.kind == "SCHEDULE" and (self.scheduled_at is None or self.due_at is not None):
            raise ValueError("일정에는 scheduledAt을 입력하고 dueAt은 비워 주세요.")
        item_at = self.due_at if self.kind == "TASK" else self.scheduled_at
        if item_at is not None and self.reminder_at > item_at:
            raise ValueError("알림 시각은 일정·마감 시각 이후일 수 없습니다.")
        return self


class TaskSuggestionConfirmIn(ConfirmedFields):
    expected_version: int = Field(ge=1)


class ConfirmedTaskUpdateIn(ConfirmedFields):
    """확인한 내용을 전부 다시 보낸다. 누락 필드는 암묵적으로 보존하지 않는다."""

    expected_version: int = Field(ge=1)


class ConfirmedTaskCancelIn(CamelModel):
    expected_version: int = Field(ge=1)


class TaskReminderOut(CamelModel):
    id: str
    reminder_at: UtcDateTime
    recipient_account_ids: list[str]
    status: Literal["PENDING", "SENDING", "SERVICE_ACCEPTED", "FAILED", "CANCELLED"]
    attempted_at: UtcDateTime | None
    last_error: str | None
    accepted_count: int
    failed_count: int
    version: int


class ConfirmedTaskOut(CamelModel):
    id: str
    suggestion_id: str
    kind: Literal["TASK", "SCHEDULE"]
    title: str
    description: str | None
    assignee_name: str | None
    assignee_account_id: str | None
    due_at: UtcDateTime | None
    scheduled_at: UtcDateTime | None
    timezone: str
    status: Literal["ACTIVE", "CANCELLED"]
    confirmed_by: str | None
    version: int
    created_at: UtcDateTime
    modified_at: UtcDateTime
    reminder: TaskReminderOut


class ReminderRecipientOut(CamelModel):
    account_id: str
    member_id: str
    name: str
    role: ServiceMemberRole
