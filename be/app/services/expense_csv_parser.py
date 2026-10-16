"""지출 CSV 파싱. 결정론적 코드로만 한다 — AI를 쓰지 않는다 (#112).

기대하는 헤더(대소문자 구분 안 함, 순서 무관): date, amount 필수.
merchant, description, category 는 선택.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime

REQUIRED_COLUMNS = {"date", "amount"}
KNOWN_COLUMNS = REQUIRED_COLUMNS | {"merchant", "description", "category"}


@dataclass
class ParsedRow:
    row_no: int
    spent_at: datetime | None
    merchant: str | None
    amount: int | None
    description: str | None
    category: str | None
    raw_fields: dict[str, str]
    validation_errors: dict[str, str] = field(default_factory=dict)


class CsvFormatError(Exception):
    """헤더 자체를 못 읽을 때. 행 단위 오류는 ParsedRow.validation_errors로 담는다."""


def _parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_expense_csv(content: bytes) -> list[ParsedRow]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("UTF-8로 읽을 수 없습니다.") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvFormatError("헤더가 없습니다.")

    headers = {name.strip().lower() for name in reader.fieldnames}
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise CsvFormatError(f"필수 열이 없습니다: {', '.join(sorted(missing))}")

    rows: list[ParsedRow] = []
    for row_no, raw_row in enumerate(reader, start=1):
        normalized = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in raw_row.items()
            if key
        }
        errors: dict[str, str] = {}

        spent_at = _parse_date(normalized.get("date", ""))
        if spent_at is None:
            # API 응답의 validation_errors 키는 API 필드명(spent_at)으로 통일한다.
            # CSV 열 이름(date)과는 다르다.
            errors["spent_at"] = "날짜를 읽을 수 없습니다 (YYYY-MM-DD)."

        amount: int | None = None
        amount_raw = normalized.get("amount", "")
        try:
            amount = int(amount_raw.replace(",", ""))
        except ValueError:
            errors["amount"] = "금액을 정수로 읽을 수 없습니다."

        rows.append(
            ParsedRow(
                row_no=row_no,
                spent_at=spent_at,
                merchant=normalized.get("merchant") or None,
                amount=amount,
                description=normalized.get("description") or None,
                category=normalized.get("category") or None,
                raw_fields=normalized,
                validation_errors=errors,
            )
        )
    return rows
