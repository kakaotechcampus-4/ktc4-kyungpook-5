"""인증 · 세션.

한 행이 신원(provider)과 세션(refresh_token)을 함께 들고 있어 로그인할 때마다
행이 쌓인다. 그래서 (provider, provider_user_id)에 유니크 제약을 걸 수 없다.
인증 방식(JWT vs 세션)이 확정되면 신원과 세션을 분리할지 다시 본다.
"""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AuthProvider
from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, enum_column, fk
from app.models.clubs import Member


class Auth(IdMixin, TimestampMixin, Base):
    __tablename__ = "auth"
    __id_prefix__ = "ath"

    member_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False, index=True
    )
    provider: Mapped[AuthProvider] = mapped_column(
        enum_column(AuthProvider), nullable=False
    )
    # 소셜 로그인 사용자 ID. LOCAL이면 null.
    provider_user_id: Mapped[str | None] = mapped_column(String(255))
    # 원문을 저장하지 않는다.
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 로그아웃 시각. null이면 아직 유효한 세션.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member: Mapped[Member] = relationship()
