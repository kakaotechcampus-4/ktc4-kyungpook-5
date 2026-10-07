"""청킹이 원문 위치를 지키며 기록을 나누는지 검증한다."""

import json
from pathlib import Path

from app.ai.contracts import RecordBlock, SourceLocation
from app.ai.features.retrieval.chunking import CHUNK_MAX_CHARS, chunk_ledger

FIXTURES = Path(__file__).parent / "fixtures" / "records"


def _fixture_blocks(name: str) -> list[RecordBlock]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return [RecordBlock.model_validate(block) for block in data["parse_result"]["blocks"]]


def _rows(sheet: str | None, count: int, start: int = 2, length: int = 50) -> list[RecordBlock]:
    """`length`자 행 `count`개. 시트가 없으면 CSV 라벨이다"""
    blocks = []
    for number in range(start, start + count):
        label = f"{number}행" if sheet is None else f"{sheet} · {number}행"
        text = f"{number}행: " + "가" * (length - len(f"{number}행: "))
        blocks.append(RecordBlock(text=text, location=SourceLocation(label=label)))
    return blocks


def _labels(chunks) -> list[str]:
    return [chunk.location.label for chunk in chunks]


# --- 장부 -------------------------------------------------------------------


def test_XLSX_장부는_시트별로_묶이고_라벨에_행_범위가_붙는다():
    chunks = chunk_ledger(_fixture_blocks("ledger_2025_h1"))

    assert _labels(chunks) == [
        "회비 수납 시트 · 2~15행",
        "회비 수납 시트 · 16~28행",
        "지출 시트 · 2~9행",
    ]
    assert [chunk.block_indexes for chunk in chunks] == [
        tuple(range(0, 14)),
        tuple(range(14, 27)),
        tuple(range(27, 35)),
    ]


def test_CSV_장부는_시트_없이_행_범위만_라벨에_붙는다():
    chunks = chunk_ledger(_fixture_blocks("ledger_2024_h2"))

    assert _labels(chunks) == ["2~7행"]
    assert chunks[0].block_indexes == tuple(range(6))


def test_청크_본문은_원본_행을_줄바꿈으로_이은_것이다():
    blocks = _fixture_blocks("ledger_2024_h2")

    chunks = chunk_ledger(blocks)

    assert chunks[0].text == "\n".join(block.text for block in blocks)


def test_모든_행이_정확히_한_청크에_들어간다():
    """겹치지 않아야 #72에서 같은 행을 두 번 세지 않는다"""
    blocks = _fixture_blocks("ledger_2025_h1")

    chunks = chunk_ledger(blocks)

    indexes = [index for chunk in chunks for index in chunk.block_indexes]
    assert indexes == list(range(len(blocks)))


def test_청크는_최대_글자_수를_넘지_않는다():
    chunks = chunk_ledger(_rows("회비", 100))

    assert all(len(chunk.text) <= CHUNK_MAX_CHARS for chunk in chunks)


def test_마지막_청크에_몇_행만_남지_않게_고르게_나눈다():
    """앞에서부터 채우면 19행 + 2행이 된다"""
    chunks = chunk_ledger(_rows("회비", 21))

    assert [len(chunk.block_indexes) for chunk in chunks] == [11, 10]


def test_시트가_다른_행은_한_청크에_섞이지_않는다():
    chunks = chunk_ledger(_rows("회비", 3) + _rows("지출", 2))

    assert _labels(chunks) == ["회비 · 2~4행", "지출 · 2~3행"]


def test_한_행만_있으면_범위_없이_그_행을_적는다():
    chunks = chunk_ledger(_rows("지출", 1, start=5))

    assert _labels(chunks) == ["지출 · 5행"]


def test_시트_이름에_구분자가_있어도_마지막_구분자로_나눈다():
    chunks = chunk_ledger(_rows("2025 · 상반기", 2))

    assert _labels(chunks) == ["2025 · 상반기 · 2~3행"]


def test_최대_글자_수보다_긴_행은_자르지_않고_혼자_둔다():
    long_row = _rows("회비", 1, start=4, length=CHUNK_MAX_CHARS + 200)
    blocks = _rows("회비", 2) + long_row + _rows("회비", 2, start=5)

    chunks = chunk_ledger(blocks)

    assert _labels(chunks) == ["회비 · 2~3행", "회비 · 4행", "회비 · 5~6행"]
    assert chunks[1].text == long_row[0].text


def test_라벨_형식이_다른_블록은_묶지_않고_라벨_그대로_둔다():
    """추측해서 묶으면 출처가 틀릴 수 있다"""
    odd = RecordBlock(text="날짜: 2025-03-04", location=SourceLocation(label="회비 수납 시트"))
    blocks = _rows("회비 수납 시트", 2) + [odd] + _rows("회비 수납 시트", 1, start=5)

    chunks = chunk_ledger(blocks)

    assert _labels(chunks) == [
        "회비 수납 시트 · 2~3행",
        "회비 수납 시트",
        "회비 수납 시트 · 5행",
    ]
    assert [chunk.block_indexes for chunk in chunks] == [(0, 1), (2,), (3,)]
