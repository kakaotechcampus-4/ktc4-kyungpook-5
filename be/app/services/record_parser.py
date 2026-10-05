"""업로드한 기록 원본(PDF·CSV·XLSX)을 parse_result로 바꾼다.

parse_result는 Record.parse_result에 저장하고 AI 색인 입력(IndexRecordRequest.blocks)으로
그대로 넘긴다(#70). 블록 순서가 블록 번호이며 빈 블록은 넣지 않는다.

    {"blocks": [{"text": "...", "location": {"label": "..."}}]}

[합의 필요] 위치 라벨은 #71·#72 담당과 확인 중인 제안이다.
PDF "N쪽" / XLSX "{시트 이름} · N행" / CSV "N행". N은 원본의 실제 쪽·행 번호다.
"""

import csv
import io
import zipfile
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime, time
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pypdf import PdfReader
from pypdf.errors import DependencyError, PdfReadError

from app.core.enums import RecordFileType, RecordParseErrorReason

ParseResult = dict[str, list[dict[str, Any]]]


class RecordParseError(Exception):
    """파싱 실패. reason은 화면 문구를 고르는 코드, debug_message는 로그용 원문이다.

    parse_error로 저장하는 형식(키 표기)은 호출하는 쪽(#42)이 정한다.
    """

    def __init__(
        self,
        reason: RecordParseErrorReason,
        debug_message: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(debug_message)
        self.reason = reason
        self.debug_message = debug_message
        self.params = params or {}


def parse_record(content: bytes, file_type: RecordFileType) -> ParseResult:
    """원본 파일을 parse_result로 바꾼다.

    예상하지 못한 예외는 원인을 단정하지 않도록 감싸지 않는다(AI-RET-04).
    """
    parser = _PARSERS.get(file_type)
    if parser is None:
        raise RecordParseError(
            RecordParseErrorReason.UNSUPPORTED_FORMAT,
            f"지원하지 않는 형식입니다: {file_type.value}",
        )
    return {"blocks": parser(content)}


def _block(text: str, label: str) -> dict[str, Any]:
    return {"text": text, "location": {"label": label}}


def _parse_pdf(content: bytes) -> list[dict[str, Any]]:
    try:
        reader = PdfReader(io.BytesIO(content))
        # 편집만 막은 PDF는 빈 비밀번호로 풀린다. 열람 암호가 있으면 풀리지 않는다.
        if reader.is_encrypted and not reader.decrypt(""):
            # [합의 필요] 화면 문구가 "지원하지 않는 형식"이라 별도 사유 추가를 FE와 협의한다.
            raise RecordParseError(
                RecordParseErrorReason.UNSUPPORTED_FORMAT, "열람 암호가 걸린 PDF입니다"
            )
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, DependencyError) as error:
        # DependencyError: AES 암호 해제에 cryptography가 필요하다. 의존성을 늘리지 않기로 해 지원하지 않는다.
        raise RecordParseError(
            RecordParseErrorReason.UNSUPPORTED_FORMAT,
            f"PDF 파일을 열 수 없습니다: {type(error).__name__}",
        ) from error

    blocks = [
        _block(text.strip(), f"{number}쪽")
        for number, text in enumerate(pages, start=1)
        if text.strip()
    ]
    if not blocks:
        raise RecordParseError(
            RecordParseErrorReason.IMAGE_NOT_READABLE,
            "모든 페이지에 텍스트가 없습니다 (스캔 문서로 보임)",
        )
    return blocks


def _parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    try:
        # data_only: 수식 대신 엑셀이 저장해 둔 계산값을 읽는다.
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, InvalidFileException) as error:
        raise RecordParseError(
            RecordParseErrorReason.UNSUPPORTED_FORMAT,
            f"XLSX 파일을 열 수 없습니다: {type(error).__name__}",
        ) from error
    try:
        blocks: list[dict[str, Any]] = []
        for sheet in workbook.worksheets:
            # 읽기 전용 모드는 파일에 적힌 시트 크기만큼만 읽는다. 엑셀이 아닌 도구가 크기를
            # 잘못 적으면 행·열이 오류 없이 빠지므로 저장된 크기를 버리고 끝까지 읽는다.
            sheet.reset_dimensions()
            # 읽기 전용 모드의 iter_rows는 min_row와 상관없이 1행부터 준다. 1부터 세야 실제 행 번호다.
            rows = enumerate(sheet.iter_rows(min_row=1, values_only=True), start=1)
            blocks.extend(
                _table_blocks(rows, lambda number, title=sheet.title: f"{title} · {number}행")
            )
        return blocks
    finally:
        workbook.close()


# 한국어 엑셀에서 저장한 CSV는 대개 CP949다. BOM이 붙은 UTF-8도 흔하다.
_CSV_ENCODINGS = ("utf-8-sig", "cp949")


def _parse_csv(content: bytes) -> list[dict[str, Any]]:
    for encoding in _CSV_ENCODINGS:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RecordParseError(
            RecordParseErrorReason.UNSUPPORTED_FORMAT,
            "CSV 인코딩을 읽을 수 없습니다 (UTF-8·CP949 아님)",
        )
    # 레코드 순번을 행 번호로 쓴다. 따옴표 안 줄바꿈이 있으면 실제 줄 번호와 다를 수 있다.
    rows = enumerate(csv.reader(io.StringIO(text)), start=1)
    return _table_blocks(rows, lambda number: f"{number}행")


def _table_blocks(
    rows: Iterable[tuple[int, Sequence[object]]], label: Callable[[int], str]
) -> list[dict[str, Any]]:
    """처음으로 비어 있지 않은 행을 열 이름으로, 이후 행을 하나씩 블록으로 만든다.

    제목 줄이 위에 있는 장부는 고려하지 않은 규칙이다. 장부 파싱 규칙이 정해지면 바꾼다.
    """
    header: list[str] | None = None
    blocks: list[dict[str, Any]] = []
    for number, cells in rows:
        values = [_cell_text(cell) for cell in cells]
        if not any(values):
            continue
        if header is None:
            header = values
            continue
        blocks.append(_block(_row_text(header, values), label(number)))
    return blocks


def _row_text(header: list[str], values: list[str]) -> str:
    """'열 이름: 값'을 잇는다. 행만 떼어 봐도 무슨 값인지 알 수 있게 한다(PR #88).

    이름 없는 열은 '열N'으로 부르고, 이름도 값도 없는 칸은 뺀다.
    """
    pairs: list[str] = []
    for index in range(max(len(header), len(values))):
        name = header[index] if index < len(header) else ""
        value = values[index] if index < len(values) else ""
        if not name and not value:
            continue
        name = name or f"열{index + 1}"
        pairs.append(f"{name}: {value}" if value else f"{name}:")
    return ", ".join(pairs)


def _cell_text(value: object) -> str:
    """셀 값을 원래 값 그대로 적는다. 쉼표 등 셀 표시 형식은 따르지 않는다.

    [합의 필요] 표시 형식(45,000)을 따를지는 #72 평가 결과를 보고 정한다.
    """
    if value is None:
        return ""
    # datetime은 date의 하위 타입이라 먼저 본다.
    if isinstance(value, datetime):
        if value.time() == time():
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


_PARSERS: dict[RecordFileType, Callable[[bytes], list[dict[str, Any]]]] = {
    RecordFileType.PDF: _parse_pdf,
    RecordFileType.CSV: _parse_csv,
    RecordFileType.XLSX: _parse_xlsx,
}
