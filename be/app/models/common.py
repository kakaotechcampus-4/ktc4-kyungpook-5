"""도메인에 묶이지 않는 공용 인프라 테이블."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, fk


class IdempotencyKey(IdMixin, TimestampMixin, Base):
    """Idempotency-Key 헤더로 받은 요청의 처리 상태와 원래 응답을 보관한다.

    같은 (member_id, endpoint, key)로 다시 오면 저장된 응답을 그대로 돌려준다.
    요청 본문 해시가 다르면 409로 막는다 — services에서 비교한다.
    """

    __tablename__ = "idempotency_keys"
    __id_prefix__ = "idm"
    __table_args__ = (
        UniqueConstraint(
            "member_id",
            "endpoint",
            "idempotency_key",
            name="uq_idempotency_member_endpoint_key",
        ),
    )

    # club 범위 밖 endpoint(예: 로그아웃)는 null.
    club_id: Mapped[str | None] = mapped_column(String(ID_LENGTH), fk("clubs.id"))
    member_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # PROCESSING / COMPLETED. 응답을 만들기 전에 PROCESSING으로 먼저 찍어
    # 동시 요청이 겹치는 창을 줄인다.
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
