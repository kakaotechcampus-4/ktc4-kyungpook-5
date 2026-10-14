"""계획 단계에서 쓰는 챗봇 대화.

동아리 기록 챗봇(R1)은 세션을 저장하지 않으므로 여기에 남기지 않는다.
그쪽 호출 이력은 AgentLog(feature=RETRIEVAL)에만 남는다.
"""

from typing import TYPE_CHECKING

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MessageRole
from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, enum_column, fk

if TYPE_CHECKING:
    from app.models.clubs import Member
    from app.models.events import Event


class Conversation(IdMixin, TimestampMixin, Base):
    """행사 하나에 대화가 여러 개 달릴 수 있다.

    계획을 이어서 진행할 때 어느 대화를 복원할지 정하는 규칙은 아직 없다.
    현재는 가장 최근 대화를 쓴다. AI-PLAN-08 구현 시 다시 본다.
    """

    __tablename__ = "conversations"
    __id_prefix__ = "cnv"

    member_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("events.id"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(100))

    member: Mapped["Member"] = relationship()
    event: Mapped["Event"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.seq"
    )


class Message(IdMixin, TimestampMixin, Base):
    """USER/ASSISTANT: 계획 대화 한 턴 (conversation_id·seq 필수).

    SYSTEM: 에이전트가 왜 그 방향을 골랐는지 조회하는 로그 — 쌩로그가 아니라
    "AI가 한 일 + 출처 근거"를 정리한 텍스트다. step_id/action_id로 바로 찾으며,
    운영 중(ON_GOING) 생기는 CONFIRMATION 판단처럼 대화 자체가 없는 경우를 위해
    conversation_id는 없을 수 있다. 출처를 구조화된 필드로 분리할지는 기록 검색
    계약(#70)이 정해진 뒤 재검토한다.
    """

    __tablename__ = "messages"
    __id_prefix__ = "msg"
    __table_args__ = (
        # created_at만으로 정렬하면 같은 시각에 들어온 메시지 순서가 흔들린다.
        # conversation_id가 둘 다 NULL인 SYSTEM 로그끼리는 PostgreSQL이 서로
        # 다른 값으로 보므로 이 제약에 걸리지 않는다.
        UniqueConstraint("conversation_id", "seq", name="uq_messages_conversation_seq"),
    )

    conversation_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("conversations.id")
    )
    step_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), fk("steps.id"))
    action_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), fk("actions.id"))
    # 대화 턴 순서. SYSTEM 로그는 대화가 아니라 쓰지 않는다.
    seq: Mapped[int | None] = mapped_column(Integer)
    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    conversation: Mapped["Conversation | None"] = relationship(back_populates="messages")
