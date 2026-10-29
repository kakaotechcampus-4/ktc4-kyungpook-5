"""영수 내역 기록 도메인 오케스트레이션 (#133).

CSV는 결정론적으로 파싱하고, 영수증 이미지는 더미 OCR(services/receipt_ocr_stub.py)로
초안을 만든다. 이미지 OCR은 agent_jobs 작업으로 기록하지만 실제 작업 큐가 없어
둘 다 요청 안에서 즉시 처리한다. 나중에 큐로 옮겨도 라우터 계약은 그대로 쓸 수
있게 서비스 함수 경계를 나눠둔다.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AgentJobKind,
    AgentJobStage,
    ExpenseSource,
    ReceiptImportStatus,
    ReceiptImportType,
    RecordCategory,
    RecordFileType,
    RecordParseStatus,
)
from app.core.exceptions import (
    ExpenseNotFound,
    ImportNotReady,
    ReceiptImportNotFound,
    ValidationFailed,
    VersionConflict,
)
from app.infra.storage import save_file
from starlette.concurrency import run_in_threadpool
from app.models.accounting import Expense, ReceiptImport, ReceiptImportRow
from app.models.records import Record
from app.schemas.accounting import ExpenseRowDraftIn
from app.services import agent_job_service
from app.services.expense_csv_parser import CsvFormatError, parse_expense_csv
from app.services.receipt_ocr_stub import extract_receipt


async def create_expense(
    session: AsyncSession,
    *,
    club_id: str,
    event_id: str | None,
    spent_at: datetime,
    merchant: str | None,
    amount: int,
    currency,
    category: str | None,
    description: str | None,
    created_by: str,
) -> Expense:
    expense = Expense(
        club_id=club_id,
        event_id=event_id,
        spent_at=spent_at,
        merchant=merchant,
        amount=amount,
        currency=currency,
        category=category,
        description=description,
        source=ExpenseSource.MANUAL,
        created_by=created_by,
    )
    session.add(expense)
    await session.commit()
    return expense


async def get_expense(session: AsyncSession, *, club_id: str, expense_id: str) -> Expense:
    expense = await session.get(Expense, expense_id)
    if expense is None or expense.club_id != club_id:
        raise ExpenseNotFound()
    return expense


async def list_expenses(
    session: AsyncSession, *, club_id: str, page: int, size: int
) -> tuple[list[Expense], int]:
    total = await session.scalar(
        select(func.count()).select_from(Expense).where(Expense.club_id == club_id)
    )
    rows = await session.scalars(
        select(Expense)
        .where(Expense.club_id == club_id)
        .order_by(Expense.spent_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows), total or 0


async def create_receipt_import(
    session: AsyncSession,
    *,
    club_id: str,
    event_id: str | None,
    import_type: ReceiptImportType,
    file_name: str,
    file_bytes: bytes,
    created_by: str,
) -> ReceiptImport:
    storage_key = await run_in_threadpool(save_file, club_id, file_name, file_bytes)
    record = Record(
        club_id=club_id,
        event_id=event_id,
        file_name=file_name,
        file_type=(
            RecordFileType.CSV
            if import_type == ReceiptImportType.EXPENSE_CSV
            else RecordFileType.IMAGE
        ),
        category=RecordCategory.RECEIPT,
        storage_key=storage_key,
        size=len(file_bytes),
        parse_status=RecordParseStatus.COMPLETED,
    )
    session.add(record)
    await session.flush()

    receipt_import = ReceiptImport(
        club_id=club_id,
        event_id=event_id,
        record_id=record.id,
        type=import_type,
        status=ReceiptImportStatus.PROCESSING,
        created_by=created_by,
    )
    session.add(receipt_import)
    await session.flush()

    if import_type == ReceiptImportType.EXPENSE_CSV:
        try:
            parsed_rows = parse_expense_csv(file_bytes)
        except CsvFormatError as exc:
            receipt_import.status = ReceiptImportStatus.FAILED
            receipt_import.error = {"reason": "COLUMN_MISMATCH", "message": str(exc)}
            await session.commit()
            # rows가 하나도 없어도, 호출부(_import_out)가 .rows에 접근할 때
            # 비동기 세션에서 지연 로딩이 일어나지 않도록 미리 채워둔다.
            await session.refresh(receipt_import, attribute_names=["rows"])
            return receipt_import

        for parsed in parsed_rows:
            session.add(
                ReceiptImportRow(
                    receipt_import_id=receipt_import.id,
                    row_no=parsed.row_no,
                    spent_at=parsed.spent_at,
                    merchant=parsed.merchant,
                    amount=parsed.amount,
                    category=parsed.category,
                    description=parsed.description,
                    raw_fields=parsed.raw_fields,
                    validation_errors=parsed.validation_errors or None,
                )
            )
    else:
        job = await agent_job_service.create_job(
            session, club_id=club_id, kind=AgentJobKind.RECEIPT_OCR, created_by=created_by
        )
        receipt_import.job_id = job.id
        agent_job_service.start(session, job, AgentJobStage.OCR)
        extracted_rows = extract_receipt(file_bytes)
        agent_job_service.succeed(session, job, {"receiptImportId": receipt_import.id})
        for row_no, extracted in enumerate(extracted_rows, start=1):
            session.add(
                ReceiptImportRow(
                    receipt_import_id=receipt_import.id,
                    row_no=row_no,
                    spent_at=extracted.spent_at,
                    merchant=extracted.merchant,
                    amount=extracted.amount,
                    category=extracted.category,
                    description=extracted.description,
                    raw_fields=extracted.raw_fields,
                    field_confidence=extracted.field_confidence or None,
                )
            )

    receipt_import.status = ReceiptImportStatus.NEEDS_REVIEW
    await session.commit()
    await session.refresh(receipt_import, attribute_names=["rows"])
    return receipt_import


async def get_receipt_import(
    session: AsyncSession, *, club_id: str, import_id: str
) -> ReceiptImport:
    receipt_import = await session.get(ReceiptImport, import_id)
    if receipt_import is None or receipt_import.club_id != club_id:
        raise ReceiptImportNotFound()
    await session.refresh(receipt_import, attribute_names=["rows"])
    return receipt_import


async def list_receipt_imports(
    session: AsyncSession, *, club_id: str, page: int, size: int
) -> tuple[list[ReceiptImport], int]:
    total = await session.scalar(
        select(func.count())
        .select_from(ReceiptImport)
        .where(ReceiptImport.club_id == club_id)
    )
    rows = await session.scalars(
        select(ReceiptImport)
        .where(ReceiptImport.club_id == club_id)
        .order_by(ReceiptImport.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows), total or 0


async def update_draft(
    session: AsyncSession,
    *,
    club_id: str,
    import_id: str,
    expected_version: int,
    row_edits: list[ExpenseRowDraftIn],
) -> ReceiptImport:
    receipt_import = await get_receipt_import(session, club_id=club_id, import_id=import_id)
    if receipt_import.version != expected_version:
        raise VersionConflict()
    if receipt_import.status != ReceiptImportStatus.NEEDS_REVIEW:
        raise ImportNotReady()

    rows_by_no = {row.row_no: row for row in receipt_import.rows}
    for position, edit in enumerate(row_edits, start=1):
        row = rows_by_no.get(edit.row_no or position)
        if row is None:
            continue
        submitted: dict[str, object] = {}
        if edit.spent_at is not None:
            row.spent_at = edit.spent_at
            submitted["spent_at"] = edit.spent_at.isoformat()
        if edit.merchant is not None:
            row.merchant = edit.merchant
            submitted["merchant"] = edit.merchant
        if edit.amount is not None:
            row.amount = edit.amount
            submitted["amount"] = edit.amount
        if edit.category is not None:
            row.category = edit.category
            submitted["category"] = edit.category
        if edit.description is not None:
            row.description = edit.description
            submitted["description"] = edit.description

        row.draft_fields = {**(row.draft_fields or {}), **submitted}
        remaining_errors = dict(row.validation_errors or {})
        for field_name in submitted:
            remaining_errors.pop(field_name, None)
        row.validation_errors = remaining_errors or None

    receipt_import.version += 1
    await session.commit()
    await session.refresh(receipt_import, attribute_names=["rows"])
    return receipt_import


async def confirm_receipt_import(
    session: AsyncSession,
    *,
    club_id: str,
    import_id: str,
    expected_version: int,
    confirmed_by: str,
) -> tuple[ReceiptImport, list[str]]:
    receipt_import = await get_receipt_import(session, club_id=club_id, import_id=import_id)
    if receipt_import.version != expected_version:
        raise VersionConflict()
    if receipt_import.status != ReceiptImportStatus.NEEDS_REVIEW:
        raise ImportNotReady()

    rows = receipt_import.rows
    blocking_errors = {
        row.row_no: row.validation_errors
        for row in rows
        if row.validation_errors or row.amount is None or row.spent_at is None
    }
    if blocking_errors:
        raise ValidationFailed(
            {f"rows[{row_no}]": "금액·날짜를 확인해 주세요." for row_no in blocking_errors}
        )

    source = (
        ExpenseSource.CSV_IMPORT
        if receipt_import.type == ReceiptImportType.EXPENSE_CSV
        else ExpenseSource.OCR_IMPORT
    )
    expense_ids: list[str] = []
    for row in rows:
        expense = Expense(
            club_id=club_id,
            event_id=receipt_import.event_id,
            spent_at=row.spent_at,
            merchant=row.merchant,
            amount=row.amount,
            currency=row.currency,
            category=row.category,
            description=row.description,
            source=source,
            receipt_record_id=receipt_import.record_id,
            created_by=confirmed_by,
        )
        session.add(expense)
        await session.flush()
        row.confirmed_expense_id = expense.id
        expense_ids.append(expense.id)

    receipt_import.status = ReceiptImportStatus.CONFIRMED
    receipt_import.confirmed_by = confirmed_by
    receipt_import.confirmed_at = datetime.now(UTC)
    await session.commit()
    return receipt_import, expense_ids
