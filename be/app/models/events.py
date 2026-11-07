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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ActionContentSource,
    ActionContentStatus,
    ActionStatus,
    ActionType,
    EventStatus,
    EventType,
    PlanReviewStatus,
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
    # 계획이 실제로 바뀔 때마다 +1. AI 검토가 어느 시점의 계획을 봤는지 가리킨다(#177).
    plan_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    club: Mapped["Club"] = relationship(back_populates="events")
    steps: Mapped[list["Step"]] = relationship(
        back_populates="event", order_by="Step.step_order"
    )
    actions: Mapped[list["Action"]] = relationship(back_populates="event")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="event")
    participants: Mapped[list["Participant"]] = relationship(back_populates="event")
    cancel_tasks: Mapped[list["EventCancelTask"]] = relationship(back_populates="event", cascade="all, delete-orphan", order_by="EventCancelTask.task_order")


class EventCancelTask(IdMixin, TimestampMixin, Base):
    __tablename__ = "event_cancel_tasks"
    __id_prefix__ = "ect"
    # 기존 20261102 migration의 인덱스와 맞춰 Alembic이 삭제로 판단하지 않게 한다.
    __table_args__ = (Index("ix_event_cancel_tasks_event_order", "event_id", "task_order", unique=True),)
    event_id: Mapped[str] = mapped_column(String(ID_LENGTH), fk("events.id", ondelete="CASCADE"), nullable=False)
    task_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[str | None] = mapped_column(String(ID_LENGTH), fk("members.id", ondelete="SET NULL"))
    event: Mapped["Event"] = relationship(back_populates="cancel_tasks")


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
    # 일정 수정의 낙관적 잠금. 기존 행은 migration에서 1로 시작한다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
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
    # 본문 초안 (#334). 운영 중 공지·발송 Action이 현재 단계가 되면 토리가 content를 채운다.
    # 기존 행은 migration에서 NONE으로 시작한다.
    content_status: Mapped[ActionContentStatus] = mapped_column(
        enum_column(ActionContentStatus),
        nullable=False,
        default=ActionContentStatus.NONE,
        server_default=ActionContentStatus.NONE.value,
    )
    # 누가 쓴 본문인지. null은 본문 없음. USER면 토리가 덮어쓰지 않는다.
    content_source: Mapped[ActionContentSource | None] = mapped_column(
        enum_column(ActionContentSource)
    )
    # 본문의 [ ] 자리표시(토리가 비워 둔 곳). 예: ["신청 링크"]. 운영진이 고치면 비운다.
    content_unknowns: Mapped[list[str]] = mapped_column(
        JsonB, nullable=False, default=list, server_default=text("'[]'")
    )
    # 초안 시도 표지. 늦게 온 옛 시도의 결과를 버리고(draft_attempt_id), 서버 재시작으로
    # 멈춘 작성을 3분 뒤 실패로 본다(draft_started_at).
    draft_attempt_id: Mapped[str | None] = mapped_column(String(32))
    draft_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 실패 이유. AI_UNAVAILABLE / AI_INVALID_RESPONSE / INTERNAL_ERROR
    draft_error_code: Mapped[str | None] = mapped_column(String(64))
    # 되돌릴 수 없는 작업인지 (사실)
    irreversible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 승인을 받아야 하는지 (정책 판정)
    approve_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[ActionStatus] = mapped_column(
        enum_column(ActionStatus), nullable=False, default=ActionStatus.PENDING
    )
    # 낙관적 잠금. 승인·거절·응답·내용 수정이 성공할 때마다 +1 (#41, #106).
    # 클라이언트가 본 버전과 다르면 본 적 없는 내용을 승인하지 않도록 409로 막는다.
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
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


class PlanReview(IdMixin, TimestampMixin, Base):
    """계획 수정 후 AI 검토. 행사당 한 행.

    events에 쓰면 modified_at이 올라 사용자 수정으로 읽히므로(onupdate) 검토 상태와
    기준 스냅샷은 이 테이블에 따로 둔다.
    """

    __tablename__ = "plan_reviews"
    __id_prefix__ = "prv"
    __table_args__ = ({"comment": "계획 수정 후 AI 검토"},)

    event_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("events.id"), nullable=False, unique=True
    )
    # 초안 생성 직후 계획 모양. 검토가 "사용자가 무엇을 바꿨는지"를 비교하는 기준이다.
    baseline: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    generated_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PlanReviewStatus] = mapped_column(
        enum_column(PlanReviewStatus),
        nullable=False,
        default=PlanReviewStatus.NOT_REQUESTED,
    )
    request_id: Mapped[str | None] = mapped_column(String(100))
    reviewed_revision: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(32))
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
