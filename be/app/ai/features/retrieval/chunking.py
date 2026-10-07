"""기록 블록을 검색 단위(청크)로 나눈다.

장부(CSV·XLSX): 같은 시트의 행을 묶는다. 행마다 열 이름이 붙어 있어 겹치지 않는다.
문서(PDF·텍스트): 쪽 안을 제목(장·조·번호 소제목)으로 나눈다. 길면 줄 경계에서 겹치게 자른다.
"""

import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from ...contracts import RecordBlock, SourceLocation
from .schemas import TextChunk

# 청크 하나의 최대 글자 수. 장부에서 이보다 긴 행 하나는 자르지 않고 혼자 둔다
CHUNK_MAX_CHARS = 1000

# 문서를 자를 때 앞 청크의 끝부분을 다음 청크 앞에 다시 넣는 길이.
# 경계에 걸친 문장이 한쪽에서는 앞뒤 문맥과 함께 남게 한다
CHUNK_OVERLAP_CHARS = 150

# 파서가 만드는 장부 라벨: "{시트} · N행"(XLSX), "N행"(CSV)
_ROW_LABEL = re.compile(r"^(?:(?P<sheet>.+) · )?(?P<row>\d+)행$")

# 문서 제목 줄
_CHAPTER = re.compile(r"^제\s*\d+\s*장(?=\s|$)")  # 제3장 회비 (줄 전체가 제목)
_ARTICLE = re.compile(r"^제\s*\d+\s*조(?:\([^)]*\))?(?=\s|$)")  # 제10조(참가비 환불) 본문...
_NUMBERED = re.compile(r"^\d+\.\s+\S")  # 1. 행사 개요 (줄 전체가 제목)
# 제목으로 볼 수 있는 최대 길이. 번호 소제목과 문서 맨 앞 제목 줄에 쓴다
_TITLE_MAX_CHARS = 30
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


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


# --- 문서 ----------------------------------------------------------------------


@dataclass
class _Section:
    title: str | None  # 라벨에 붙일 제목. 첫 제목 앞부분은 None
    lines: list[str]
    has_body: bool  # 제목 말고 내용이 있는지


def chunk_document(blocks: Sequence[RecordBlock]) -> list[TextChunk]:
    """쪽(블록)마다 제목으로 나눠 청크로 만든다. 쪽을 넘어 묶지 않는다.

    라벨은 "2쪽 · 제10조(참가비 환불)"처럼 쪽 + 제목 원문이다. 제목이 없으면 쪽만 쓴다.
    """
    chunks: list[TextChunk] = []
    for index, block in enumerate(blocks):
        page = block.location.label
        for title, lines in _attach_titles(_sections(block.text)):
            location = SourceLocation(label=page if title is None else f"{page} · {title}")
            chunks += [
                TextChunk(text="\n".join(window), location=location, block_indexes=(index,))
                for window in _windows(lines)
            ]
    return chunks


def _sections(text: str) -> list[_Section]:
    """제목 줄이 나올 때마다 새 섹션을 연다. 빈 줄은 버린다"""
    # 줄마다 제목인지를 판별, 섹션으로 나눈다.

    sections: list[_Section] = []
    in_article = False  # 조 안의 "1. ..." 줄은 제목이 아니라 그 조의 항목이다

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _CHAPTER.match(stripped):
            in_article = False
            sections.append(_Section(stripped, [line], has_body=False))
        elif article := _ARTICLE.match(stripped):
            # 조는 제목 뒤에 본문이 같은 줄로 이어진다. 라벨에는 제목 부분만 쓴다
            in_article = True
            sections.append(_Section(article.group(), [line], stripped != article.group()))
        elif not in_article and _is_numbered_title(stripped):
            sections.append(_Section(stripped, [line], has_body=False))
        elif sections:
            sections[-1].lines.append(line)
            sections[-1].has_body = True
        else:
            sections.append(_Section(None, [line], has_body=True))

    # 쪽 맨 앞의 짧은 한 줄은 문서 제목으로 본다 (예: "2025 봄 MT 결과보고")
    first = sections[0] if sections else None
    if first and first.title is None and len(first.lines) == 1:
        first.has_body = len(first.lines[0].strip()) > _TITLE_MAX_CHARS
    return sections


def _is_numbered_title(line: str) -> bool:
    """"1. 행사 개요"는 제목, "1. 7일 전까지: 전액"·"1. 회비를 낸다."는 항목"""
    return (
        _NUMBERED.match(line) is not None
        and len(line) <= _TITLE_MAX_CHARS
        and ":" not in line
        and not line.rstrip(".").endswith("다")
    )


def _attach_titles(sections: list[_Section]) -> Iterator[tuple[str | None, list[str]]]:
    """제목만 있는 섹션은 혼자 두지 않고 다음 섹션 앞에 붙인다.

    "제3장 회비" + "제8조(...) ..." → 한 청크, 라벨은 더 구체적인 제8조.
    """
    pending: list[str] = []
    for section in sections:
        pending += section.lines
        if section.has_body:
            yield section.title, pending
            pending = []
    if pending:  # 쪽 끝에 제목만 남아도 버리지 않는다
        yield sections[-1].title, pending


def _windows(lines: list[str]) -> list[list[str]]:
    """줄 경계에서 CHUNK_MAX_CHARS 이하로 자른다. 다음 조각은 앞 조각의 끝 줄로 시작한다"""

    windows: list[list[str]] = []
    current: list[str] = []
    for line in _fit_lines(lines):
        if current and _joined_length([*current, line]) > CHUNK_MAX_CHARS:
            windows.append(current)
            current = _overlap(current)
            if _joined_length([*current, line]) > CHUNK_MAX_CHARS:
                current = []
        current.append(line)
    windows.append(current)
    return windows


def _overlap(lines: list[str]) -> list[str]:
    """끝에서부터 CHUNK_OVERLAP_CHARS 안에 드는 줄들.

    첫 줄은 넣지 않는다. 조각 전체가 다시 들어가 같은 조각이 반복되는 것을 막는다.
    """
    tail: list[str] = []
    for line in reversed(lines[1:]):
        if _joined_length([line, *tail]) > CHUNK_OVERLAP_CHARS:
            break
        tail.insert(0, line)
    return tail


def _fit_lines(lines: list[str]) -> Iterator[str]:
    """CHUNK_MAX_CHARS보다 긴 줄은 문장 끝에서 나눈다. 문장 하나가 더 길면 글자 수로 자른다"""
    for line in lines:
        if len(line) <= CHUNK_MAX_CHARS:
            yield line
            continue
        piece = ""
        for sentence in _SENTENCE_END.split(line):
            for start in range(0, len(sentence), CHUNK_MAX_CHARS):
                part = sentence[start : start + CHUNK_MAX_CHARS]
                if piece and len(piece) + 1 + len(part) > CHUNK_MAX_CHARS:
                    yield piece
                    piece = part
                else:
                    piece = f"{piece} {part}" if piece else part
        yield piece


def _joined_length(lines: list[str]) -> int:
    """줄바꿈으로 이었을 때의 길이"""
    return sum(len(line) for line in lines) + len(lines) - 1
