"""영수 내역 기록 도메인 요청·응답 스키마 (#133)."""

from datetime import date

from app.core.enums import (
    CurrencyCode,
    ExpenseSource,
    ReceiptImportStatus,
    ReceiptImportType,
)
from app.schemas.common import CamelModel, PageMeta, UtcDateTime


class ExpenseCreateIn(CamelModel):
    spent_at: UtcDateTime
    merchant: str | None = None
    amount: int
    currency: CurrencyCode = CurrencyCode.KRW
    category: str | None = None
    description: str | None = None
    event_id: str | None = None


class ExpenseOut(CamelModel):
    id: str
    spent_at: UtcDateTime
    merchant: str | None
    amount: int
    currency: CurrencyCode
    category: str | None
    description: str | None
    source: ExpenseSource
    receipt_record_id: str | None
    version: int


class ExpenseListResponse(CamelModel):
    data: list[ExpenseOut]
    meta: PageMeta


class ReceiptImportRowOut(CamelModel):
    id: str
    row_no: int
    spent_at: UtcDateTime | None
    merchant: str | None
    amount: int | None
    currency: CurrencyCode
    category: str | None
    description: str | None
    field_confidence: dict[str, float] | None
    validation_errors: dict[str, str] | None
    confirmed_expense_id: str | None


class ReceiptImportOut(CamelModel):
    id: str
    type: ReceiptImportType
    status: ReceiptImportStatus
    version: int
    error: dict[str, object] | None
    rows: list[ReceiptImportRowOut]


class ReceiptImportListItemOut(CamelModel):
    id: str
    type: ReceiptImportType
    status: ReceiptImportStatus
    version: int


class ReceiptImportListResponse(CamelModel):
    data: list[ReceiptImportListItemOut]
    meta: PageMeta


class ExpenseRowDraftIn(CamelModel):
    """draft 수정 한 행. 사람이 고친 값만 보낸다 — 안 보낸 필드는 그대로 둔다."""

    row_no: int
    spent_at: date | None = None
    merchant: str | None = None
    amount: int | None = None
    category: str | None = None
    description: str | None = None


class ReceiptImportDraftIn(CamelModel):
    expected_version: int
    expense_rows: list[ExpenseRowDraftIn]


class ReceiptImportConfirmIn(CamelModel):
    expected_version: int


class ReceiptImportConfirmOut(CamelModel):
    expense_ids: list[str]
