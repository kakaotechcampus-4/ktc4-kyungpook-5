"""기록 블록을 검색 단위(청크)로 나눈다.

장부(CSV·XLSX): 같은 시트의 행을 묶는다. 행마다 열 이름이 붙어 있어 겹치지 않는다.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from ...contracts import RecordBlock, SourceLocation
from .schemas import TextChunk

# 청크 하나의 최대 글자 수. 이보다 긴 행 하나는 자르지 않고 혼자 둔다
CHUNK_MAX_CHARS = 1000

# 파서가 만드는 장부 라벨: "{시트} · N행"(XLSX), "N행"(CSV)
_ROW_LABEL = re.compile(r"^(?:(?P<sheet>.+) · )?(?P<row>\d+)행$")


@dataclass(frozen=True)
class _Row:
    index: int  # 블록 번호
    sheet: str | None
    number: int  # 원본 행 번호
    text: str


def chunk_ledger(blocks: Sequence[RecordBlock]) -> list[TextChunk]:
    """장부 행을 시트별로 묶어 청크로 만든다.

    라벨에서 시트·행 번호를 읽지 못한 블록은 묶지 않고 혼자 둔다.
    덜 묶이는 것은 괜찮지만, 출처(라벨)가 틀리면 안 되기 때문이다.
    """
    chunks: list[TextChunk] = []
    run: list[_Row] = []  # 지금 모으는 같은 시트의 행들

    for index, block in enumerate(blocks):
        row = _parse_row(index, block)
        if run and (row is None or row.sheet != run[-1].sheet):
            chunks += [_ledger_chunk(group) for group in _split_evenly(run)]
            run = []
        if row is None:
            chunks.append(
                TextChunk(text=block.text, location=block.location, block_indexes=(index,))
            )
        else:
            run.append(row)

    if run:
        chunks += [_ledger_chunk(group) for group in _split_evenly(run)]
    return chunks


def _parse_row(index: int, block: RecordBlock) -> _Row | None:
    match = _ROW_LABEL.match(block.location.label)
    if match is None:
        return None
    return _Row(index, match["sheet"], int(match["row"]), block.text)


def _split_evenly(rows: list[_Row]) -> list[list[_Row]]:
    """상한을 넘지 않게, 크기가 비슷한 묶음으로 나눈다.

    앞에서부터 꽉 채우면 마지막에 한두 행만 남을 수 있다(27행 → 19행 + 8행).
    그래서 필요한 묶음 수를 먼저 구하고 그 크기에 맞춰 나눈다(27행 → 14행 + 13행).
    """

    # 전체 텍스트 크기 계산
    total = sum(len(row.text) for row in rows) + len(rows) - 1  # 줄바꿈 포함

    # 몇개의 chunk가 필요한지 계산
    # ex: chunk 크기 1000자, 전체가 2700자 -> ceil(2700/1000) = 3개
    # 각 chunk가 어느정도 크기면 균등한지 계산
    target = total / math.ceil(total / CHUNK_MAX_CHARS)

    groups: list[list[_Row]] = []
    current: list[_Row] = []
    size = 0

    # 행을 하나씩 chunk에 담음
    for row in rows:
        added = len(row.text) + (1 if current else 0)
        if current and (size >= target or size + added > CHUNK_MAX_CHARS):
            groups.append(current)
            current, size, added = [], 0, len(row.text)
        current.append(row)
        size += added
    groups.append(current)
    return groups


def _ledger_chunk(rows: list[_Row]) -> TextChunk:
    first, last = rows[0], rows[-1]
    span = f"{first.number}행" if len(rows) == 1 else f"{first.number}~{last.number}행"
    label = span if first.sheet is None else f"{first.sheet} · {span}"
    return TextChunk(
        text="\n".join(row.text for row in rows),
        location=SourceLocation(label=label),
        block_indexes=tuple(row.index for row in rows),
    )
