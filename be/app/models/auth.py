"""계정 · 로그인 세션.

인증 방식을 DB 세션으로 정하면서(#131) 신원(Account)과 세션(Auth)을 분리했다.
로그아웃·비밀번호 변경·계정 정지 때 세션을 즉시 끊어야 해서, 토큰 내용만으로
유효성을 판단하는 stateless 방식 대신 매 요청마다 DB로 확인하는 쪽을 택했다.

LOCAL과 KAKAO 두 로그인 수단만 쓴다. 공급자가 둘뿐이라 범용 식별 테이블 대신
Account에 각 수단의 식별값(password_hash, kakao_user_id)을 바로 둔다.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, ID_LENGTH, IdMixin, TimestampMixin, fk


class Account(IdMixin, TimestampMixin, Base):
    """동아리와 무관한 로그인 신원. 가입 직후 동아리가 하나도 없는 상태를 표현한다."""

    __tablename__ = "accounts"
    __id_prefix__ = "acc"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # LOCAL 전용. 원문을 저장하지 않는다. KAKAO만 쓰는 계정은 null.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # KAKAO 전용 식별값. LOCAL만 쓰는 계정은 null.
    kakao_user_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 원문을 저장하지 않는다. 실제 메일 발송 전까지는 서버 로그로 대신 전달한다.
    email_verification_token_hash: Mapped[str | None] = mapped_column(String(255))
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class Auth(IdMixin, TimestampMixin, Base):
    """로그인 세션 한 건. 로그인마다 새 행이 생긴다."""

    __tablename__ = "auth"
    __id_prefix__ = "ath"

    account_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("accounts.id"), nullable=False, index=True
    )
    # 원문을 저장하지 않는다.
    access_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 로그아웃·강제 만료 시각. null이면 아직 유효한 세션.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship()
