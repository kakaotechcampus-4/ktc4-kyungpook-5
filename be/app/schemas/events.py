"""행사 도메인 요청·응답 스키마.

내부(모델·서비스)는 snake_case, API 경계는 camelCase다. 변환은 CamelModel이 맡고
서비스·모델 쪽은 이름을 바꾸지 않는다.

enum은 core/enums.py의 StrEnum을 그대로 쓴다. 값이 곧 API 코드라 변환이 필요 없다.
"""

from datetime import UTC, date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, PlainSerializer
from pydantic.alias_generators import to_camel

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    MemberRole,
    StepActor,
    StepState,
)


def _iso_utc(value: datetime) -> str:
    """명세의 ISO 8601 UTC 표기에 맞춘다. 기본 직렬화는 Z 대신 +00:00으로 나간다."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDateTime = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ResolvedBy(CamelModel):
    """승인·거절·확인요청을 처리한 동아리원."""

    id: str
    name: str
    role: MemberRole


class ActionOption(CamelModel):
    """CONFIRMATION 카드의 선택 버튼 하나."""

    key: str
    label: str


class ActionOut(CamelModel):
    id: str
    type: ActionType
    title: str
    subtitle: str | None
    irreversible: bool
    approve_needed: bool
    status: ActionStatus
    amount: int | None
    due_date: date | None
    # CONFIRMATION은 단계에 묶이지 않아 둘 다 null이 될 수 있다.
    step_id: str | None
    step_name: str | None
    resolved_at: UtcDateTime | None
    resolved_by: ResolvedBy | None
    deny_reason: str | None
    # CONFIRMATION 전용. payload에서 펼쳐 담으며 다른 타입은 항상 null이다.
    options: list[ActionOption] | None
    allow_manual: bool | None
    can_approve: bool


class PageMeta(CamelModel):
    page: int
    size: int
    total_count: int


class ActionListResponse(CamelModel):
    data: list[ActionOut]
    meta: PageMeta


class StepProgressOut(CamelModel):
    step_order: int
    state: StepState


class EventOut(CamelModel):
    id: str
    title: str
    status: EventStatus
    start_date: date | None
    end_date: date | None
    dday: int | None
    current_step_name: str | None
    step_progress: list[StepProgressOut]
    pending_approval_count: int
    # participants·transactions 확정 전이라 항상 null (이슈 #17)
    payment: Any | None
    budget: Any | None


class EventListResponse(CamelModel):
    data: list[EventOut]
    meta: PageMeta


class DoneActionOut(CamelModel):
    id: str
    title: str
    status: ActionStatus


class RemainingActionOut(CamelModel):
    id: str
    title: str
    status: ActionStatus
    approve_needed: bool


class StepOut(CamelModel):
    id: str
    step_order: int
    name: str
    actor: StepActor
    state: StepState
    started_time: UtcDateTime | None
    deadline: UtcDateTime | None
    completed_count: int
    total_action_count: int
    completed_at: UtcDateTime | None
    done_actions: list[DoneActionOut]
    remaining_actions: list[RemainingActionOut]


class StepListResponse(CamelModel):
    data: list[StepOut]
    meta: None = None
