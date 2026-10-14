"""행사 · 단계 · 행동.

금액은 모두 정수 원 단위로만 저장한다 (NF2).
"""

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    EventType,
    StepActor,
    StepCode,
    StepPhase,
)
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk

if TYPE_CHECKING:
    from app.models.chat import Conversation
    from app.models.clubs import Club, Member


class Event(IdMixin, TimestampMixin, Base):
    """행사. 계획 시작 시 PLANNING으로 생기고 확정 시 같은 행이 ON_GOING이 된다."""

    __tablename__ = "events"
    __id_prefix__ = "evt"
    __table_args__ = (
        Index("ix_events_club_status", "club_id", "status"),
        {"comment": "행사"},
    )

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    # 계획 생성 시점에 확정한다. 사용자가 비워두면 서버가 기본값을 넣는다.
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[EventStatus] = mapped_column(
        enum_column(EventStatus), nullable=False, default=EventStatus.PLANNING
    )
    # AI가 단계를 배열하는 근거. 저장하지 않으면 계획을 열 때마다 대화를 재해석해야 한다.
    event_type: Mapped[EventType | None] = mapped_column(enum_column(EventType))
    location: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    expected_headcount: Mapped[int | None] = mapped_column(Integer)
    budget_total: Mapped[int | None] = mapped_column(Integer)
    fee_per_person: Mapped[int | None] = mapped_column(Integer)
    # 계획 생성 시 만들어지는 부가 정보. 재생성 가능한 파생값이라 정규화하지 않는다.
    # 내부 형식은 schemas에서 고정한다. 새 부가 정보가 생기면 컬럼을 하나 더 둔다.
    plan_warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    plan_excluded_steps: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # 계획 임시 저장 시각. null이면 미저장.
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    club: Mapped["Club"] = relationship(back_populates="events")
    steps: Mapped[list["Step"]] = relationship(
        back_populates="event", order_by="Step.step_order"
    )
    actions: Mapped[list["Action"]] = relationship(back_populates="event")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="event")
    participants: Mapped[list["Participant"]] = relationship(back_populates="event")


class Step(IdMixin, TimestampMixin, Base):
    """행사 안의 업무 묶음 (사전 조사, 정산 등).

    진행률은 이 단계의 Action을 세어 서버가 계산한다. 완료 수를 컬럼으로 들고
    있으면 Action 상태가 바뀔 때마다 동기화해야 하고 어긋날 수 있다.
    Action이 없는 MANUAL 단계는 completed_at으로 완료를 판정한다.
    """

    __tablename__ = "steps"
    __id_prefix__ = "stp"
    __table_args__ = (
        # 재정렬은 여러 행의 step_order를 한 트랜잭션에서 맞바꾼다. 즉시 검사하면
        # 중간 상태에서 충돌하므로 커밋 시점까지 검사를 미룬다.
        UniqueConstraint(
            "event_id",
            "step_order",
            name="uq_steps_event_order",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    event_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("events.id"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[StepPhase] = mapped_column(enum_column(StepPhase), nullable=False)
    # 고정 카탈로그(#69 step-catalog.md) 코드. 이름·묶음·담당 조회의 기준이 된다.
    code: Mapped[StepCode] = mapped_column(enum_column(StepCode), nullable=False)
    # 카탈로그 이름의 생성 시점 스냅샷. code로 유도 가능해도, 카탈로그 문구가
    # 나중에 바뀌어도 과거 행사의 화면 문구가 흔들리지 않게 그대로 남긴다.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[StepActor] = mapped_column(enum_column(StepActor), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )

    event: Mapped["Event"] = relationship(back_populates="steps")
    actions: Mapped[list["Action"]] = relationship(back_populates="step")


class Action(IdMixin, TimestampMixin, Base):
    """Step 안에서 실제로 실행하고 기록하는 행동.

    event_id는 step_id가 없는 확인 요청(CONFIRMATION)을 위해 따로 둔다.
    step이 있을 때 action.event_id와 action.step.event_id가 같아야 하는데
    DB 제약으로는 막을 수 없으므로 services에서 보장한다.
    """

    __tablename__ = "actions"
    __id_prefix__ = "act"
    __table_args__ = (
        Index("ix_actions_event_status", "event_id", "status"),
        {"comment": "승인·실행 대상 행동"},
    )

    event_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("events.id"), nullable=False
    )
    # 단계에 묶이지 않는 확인 요청이 있어 nullable이다.
    step_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("steps.id"), index=True
    )
    type: Mapped[ActionType] = mapped_column(enum_column(ActionType), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text)
    # 승인 대상 본문 (예: 공지 문구). payload(설정값)와 달리 수정하면 재승인이
    # 필요해 생명주기가 다르므로 따로 둔다 — services에서 content가 바뀌면
    # status를 PENDING으로 되돌린다.
    content: Mapped[str | None] = mapped_column(Text)
    # 되돌릴 수 없는 작업인지 (사실)
    irreversible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 승인을 받아야 하는지 (정책 판정)
    approve_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[ActionStatus] = mapped_column(
        enum_column(ActionStatus), nullable=False, default=ActionStatus.PENDING
    )
    amount: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    # 유형별 설정값. 키는 ActionType마다 다르며 schemas에서 고정한다(#69, #106).
    # NOTICE: 올릴 곳·대상 범위 / EXTERNAL_SEND: 대상 조건
    # CONTRACT: 업체·취소 조건 / TRANSFER: 받는 곳·미납 안내 시점
    # EXPENSE: 영수증 필수·승인 방식 / CONFIRMATION: 선택지(options)·직접 입력 허용 여부
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    deny_reason: Mapped[str | None] = mapped_column(Text)
    # 승인·거절·확인요청 선택을 모두 받으므로 resolved_*로 둔다.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )

    event: Mapped["Event"] = relationship(back_populates="actions")
    step: Mapped["Step | None"] = relationship(back_populates="actions")
    resolver: Mapped["Member | None"] = relationship(foreign_keys=[resolved_by])


class Participant(IdMixin, TimestampMixin, Base):
    """동아리 전체 명단(Member)과 별개로, 이 행사에 신청했는지를 추적한다.

    미응답/응답 집계(예: "미응답 9명")는 Member 전체가 아니라 이 행에서 센다.
    """

    __tablename__ = "participants"
    __id_prefix__ = "ptp"
    __table_args__ = (
        UniqueConstraint("event_id", "member_id", name="uq_participants_event_member"),
    )

    event_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("events.id"), nullable=False
    )
    member_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )
    # null이면 미응답.
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped["Event"] = relationship(back_populates="participants")
    member: Mapped["Member"] = relationship(back_populates="participations")
