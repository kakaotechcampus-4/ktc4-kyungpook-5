"""동아리와 동아리원."""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MemberRole
from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, enum_column, fk

if TYPE_CHECKING:
    from app.models.events import Event
    from app.models.records import Record


class Club(IdMixin, TimestampMixin, Base):
    __tablename__ = "clubs"
    __id_prefix__ = "clb"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list["Member"]] = relationship(back_populates="club")
    events: Mapped[list["Event"]] = relationship(back_populates="club")
    records: Mapped[list["Record"]] = relationship(back_populates="club")


class Member(IdMixin, TimestampMixin, Base):
    """동아리원.

    email과 password_hash가 없는 행이 있을 수 있다. 계정 없이 명단에만 있는
    동아리원을 참가자·미납자 집계에 넣기 위해서다.
    """

    __tablename__ = "members"
    __id_prefix__ = "mbr"
    __table_args__ = (
        # 같은 동아리에 같은 이메일이 두 번 등록되면 로그인 시 어느 행인지 정할 수 없다.
        # email이 NULL인 행(계정 없는 동아리원)은 PostgreSQL이 중복으로 보지 않아 여럿 가능하다.
        UniqueConstraint("club_id", "email", name="uq_members_club_email"),
    )

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[MemberRole] = mapped_column(enum_column(MemberRole), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))

    club: Mapped["Club"] = relationship(back_populates="members")
