"""기록 색인: 기록을 청크로 나누고 임베딩을 붙인다."""

from collections.abc import Awaitable, Callable, Sequence

from app.core.enums import RecordFileType

from ...contracts import IndexedChunk, IndexRecordRequest, IndexRecordResult
from ...errors import AIEmptyRecordError
from ...llm import aembed_texts
from .chunking import chunk_document, chunk_ledger
from .schemas import TextChunk

# 행 단위로 들어오는 장부. 나머지(PDF·텍스트 기록)는 문서로 처리한다
_LEDGER_TYPES = {RecordFileType.CSV, RecordFileType.XLSX}

Embed = Callable[[Sequence[str]], Awaitable[list[tuple[float, ...]]]]


async def index_record_chunks(
    request: IndexRecordRequest, *, embed: Embed = aembed_texts
) -> IndexRecordResult:
    """기록을 청크로 나누고 임베딩한다. 테스트에서는 `embed`를 가짜로 바꾼다"""
    if not request.blocks:
        raise AIEmptyRecordError("색인할 내용이 없는 기록입니다")

    chunk = chunk_ledger if request.file_type in _LEDGER_TYPES else chunk_document
    chunks = chunk(request.blocks)
    vectors = await embed([embedding_input(request.file_name, item) for item in chunks])

    return IndexRecordResult(
        chunks=tuple(
            IndexedChunk(
                text=item.text,
                location=item.location,
                block_indexes=item.block_indexes,
                embedding=vector,
            )
            for item, vector in zip(chunks, vectors, strict=True)
        )
    )


def embedding_input(file_name: str, chunk: TextChunk) -> str:
    """임베딩 API에 보낼 글. 본문 앞에 문서명과 위치를 붙인다.

    본문에 "2025 봄 MT"가 없어도 파일명으로 찾게 하기 위해서다.
    이 글은 벡터를 만드는 데만 쓰고 저장하지 않는다. 저장되는 청크 text에는 붙이지 않는다.
    text는 검색 결과로 돌아와 근거로 쓰이므로 PDF 원문과 같아야 하고,
    문서명·위치는 검색 결과에 따로 온다.
    """
    return f"문서: {file_name}\n위치: {chunk.location.label}\n\n{chunk.text}"
