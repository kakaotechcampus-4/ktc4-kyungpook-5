"""영수 내역 기록 — 직접 입력·CSV·영수증 OCR 초안 (#112, #133).

수납 대조·송금·환불·정산 보고서는 다루지 않는다. 확정된 지출 내역을 남기는
것까지만 한다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CurrencyCode,
    ExpenseSource,
    ReceiptImportStatus,
    ReceiptImportType,
)
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk


class ReceiptImport(IdMixin, TimestampMixin, Base):
    """CSV 업로드 또는 영수증 사진 한 건의 추출·검수 진행 상황."""

    __tablename__ = "receipt_imports"
    __id_prefix__ = "rim"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    # 원본 이미지/CSV. 파일 메타데이터는 records에서 공용으로 관리한다.
    record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("records.id", ondelete="SET NULL")
    )
    type: Mapped[ReceiptImportType] = mapped_column(
        enum_column(ReceiptImportType), nullable=False
    )
    status: Mapped[ReceiptImportStatus] = mapped_column(
        enum_column(ReceiptImportStatus),
        nullable=False,
        default=ReceiptImportStatus.QUEUED,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # OCR/CSV 원본 추출값. 사람이 고친 값은 receipt_import_rows의 draft_fields에 따로 둔다.
    extraction_result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    # 같은 파일 재업로드 감지용 보조 정보.
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    confirmed_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )

    rows: Mapped[list["ReceiptImportRow"]] = relationship(
        back_populates="receipt_import", order_by="ReceiptImportRow.row_no"
    )


class ReceiptImportRow(IdMixin, TimestampMixin, Base):
    """영수 내역 초안 한 행. CSV는 행마다, 영수증 사진은 항목마다 하나씩."""

    __tablename__ = "receipt_import_rows"
    __id_prefix__ = "rir"
    __table_args__ = (
        UniqueConstraint(
            "receipt_import_id", "row_no", name="uq_receipt_rows_import_rowno"
        ),
    )

    receipt_import_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("receipt_imports.id"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 영수증에 날짜만 있으면 자정으로 채운다. 시각 불확실 플래그는 두지 않는다(MVP).
    spent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merchant: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[CurrencyCode] = mapped_column(
        enum_column(CurrencyCode), nullable=False, default=CurrencyCode.KRW
    )
    # 값 집합 미정 — PM과 합의 전까지 자유 텍스트로 받는다.
    category: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    raw_fields: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    draft_fields: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    field_confidence: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    validation_errors: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    # 확정 후에만 값이 생긴다. 재확정 시 같은 expense를 재사용한다.
    confirmed_expense_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("expenses.id", ondelete="SET NULL")
    )

    receipt_import: Mapped["ReceiptImport"] = relationship(back_populates="rows")


class Expense(IdMixin, TimestampMixin, Base):
    """확정된 지출 내역. 입력 방식과 상관없이 동일한 모델을 쓴다."""

    __tablename__ = "expenses"
    __id_prefix__ = "exp"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    spent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[CurrencyCode] = mapped_column(
        enum_column(CurrencyCode), nullable=False, default=CurrencyCode.KRW
    )
    category: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[ExpenseSource] = mapped_column(
        enum_column(ExpenseSource), nullable=False
    )
    # 영수증 원본(있으면). 직접 입력은 null.
    receipt_record_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("records.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("members.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
