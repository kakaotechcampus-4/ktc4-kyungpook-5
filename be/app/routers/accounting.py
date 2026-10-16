"""영수 내역 기록 엔드포인트 (#133)."""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_club_role, require_member
from app.core.enums import MemberRole, ReceiptImportType
from app.db.session import get_session
from app.models.clubs import Member
from app.schemas.accounting import (
    ExpenseCreateIn,
    ExpenseListResponse,
    ExpenseOut,
    ReceiptImportConfirmIn,
    ReceiptImportConfirmOut,
    ReceiptImportDraftIn,
    ReceiptImportListResponse,
    ReceiptImportOut,
    ReceiptImportRowOut,
)
from app.schemas.common import Envelope, PageMeta
from app.services import accounting_service

router = APIRouter(prefix="/api/v1/clubs/{club_id}", tags=["accounting"])


def _import_out(receipt_import) -> ReceiptImportOut:
    return ReceiptImportOut(
        id=receipt_import.id,
        type=receipt_import.type,
        status=receipt_import.status,
        version=receipt_import.version,
        error=receipt_import.error,
        rows=[
            ReceiptImportRowOut(
                id=row.id,
                row_no=row.row_no,
                spent_at=row.spent_at,
                merchant=row.merchant,
                amount=row.amount,
                currency=row.currency,
                category=row.category,
                description=row.description,
                field_confidence=row.field_confidence,
                validation_errors=row.validation_errors,
                confirmed_expense_id=row.confirmed_expense_id,
            )
            for row in receipt_import.rows
        ],
    )


@router.post("/expenses", response_model=Envelope[ExpenseOut], status_code=201)
async def create_expense(
    club_id: str,
    body: ExpenseCreateIn,
    member: Member = Depends(require_club_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ExpenseOut]:
    expense = await accounting_service.create_expense(
        session,
        club_id=club_id,
        event_id=body.event_id,
        spent_at=body.spent_at,
        merchant=body.merchant,
        amount=body.amount,
        currency=body.currency,
        category=body.category,
        description=body.description,
        created_by=member.id,
    )
    return Envelope(data=ExpenseOut.model_validate(expense))


@router.get("/expenses", response_model=ExpenseListResponse)
async def list_expenses(
    club_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> ExpenseListResponse:
    rows, total = await accounting_service.list_expenses(
        session, club_id=club_id, page=page, size=size
    )
    return ExpenseListResponse(
        data=[ExpenseOut.model_validate(row) for row in rows],
        meta=PageMeta(page=page, size=size, total_count=total),
    )


@router.post(
    "/receipt-imports", response_model=Envelope[ReceiptImportOut], status_code=202
)
async def create_receipt_import(
    club_id: str,
    type: ReceiptImportType = Form(...),
    file: UploadFile = File(...),
    member: Member = Depends(require_club_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ReceiptImportOut]:
    content = await file.read()
    receipt_import = await accounting_service.create_receipt_import(
        session,
        club_id=club_id,
        event_id=None,
        import_type=type,
        file_name=file.filename or "upload",
        file_bytes=content,
        created_by=member.id,
    )
    return Envelope(data=_import_out(receipt_import))


@router.get("/receipt-imports", response_model=ReceiptImportListResponse)
async def list_receipt_imports(
    club_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> ReceiptImportListResponse:
    rows, total = await accounting_service.list_receipt_imports(
        session, club_id=club_id, page=page, size=size
    )
    return ReceiptImportListResponse(
        data=[
            {
                "id": row.id,
                "type": row.type,
                "status": row.status,
                "version": row.version,
            }
            for row in rows
        ],
        meta=PageMeta(page=page, size=size, total_count=total),
    )


@router.get(
    "/receipt-imports/{import_id}", response_model=Envelope[ReceiptImportOut]
)
async def get_receipt_import(
    club_id: str,
    import_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ReceiptImportOut]:
    receipt_import = await accounting_service.get_receipt_import(
        session, club_id=club_id, import_id=import_id
    )
    return Envelope(data=_import_out(receipt_import))


@router.patch(
    "/receipt-imports/{import_id}/draft", response_model=Envelope[ReceiptImportOut]
)
async def update_draft(
    club_id: str,
    import_id: str,
    body: ReceiptImportDraftIn,
    _member: Member = Depends(require_club_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ReceiptImportOut]:
    receipt_import = await accounting_service.update_draft(
        session,
        club_id=club_id,
        import_id=import_id,
        expected_version=body.expected_version,
        row_edits=body.expense_rows,
    )
    return Envelope(data=_import_out(receipt_import))


@router.post(
    "/receipt-imports/{import_id}/confirm",
    response_model=Envelope[ReceiptImportConfirmOut],
)
async def confirm_receipt_import(
    club_id: str,
    import_id: str,
    body: ReceiptImportConfirmIn,
    member: Member = Depends(require_club_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ReceiptImportConfirmOut]:
    expense_ids = await accounting_service.confirm_receipt_import(
        session,
        club_id=club_id,
        import_id=import_id,
        expected_version=body.expected_version,
        confirmed_by=member.id,
    )
    return Envelope(data=ReceiptImportConfirmOut(expense_ids=expense_ids))
