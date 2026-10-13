"""메모리에 청크를 두는 기록 검색 port 구현.

BE 청크 테이블·pgvector 없이 색인·검색을 개발하고 평가할 때 쓴다.
저장(add)은 BE 역할을 대신하는 테스트 입구라 port에는 없다.
"""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.core.enums import RecordCategory

from ...contracts import IndexedChunk, RecordSource
from ...ports import ChunkSearchQuery, RetrievedChunk


@dataclass(frozen=True)
class StoredRecord:
    """BE가 청크에 복사해 두는 기록 메타데이터"""

    record_id: str
    club_id: str
    file_name: str
    category: RecordCategory
    event_id: str | None = None


class InMemoryRecordSearch:
    """`RecordSearchPort` 구현. 프로그램이 끝나면 데이터가 사라진다"""

    def __init__(self) -> None:
        self._chunks: dict[str, tuple[IndexedChunk, ...]] = {}
        self._records: dict[str, StoredRecord] = {}

    def add(self, record: StoredRecord, chunks: Iterable[IndexedChunk]) -> None:
        """청크를 저장한다. 같은 기록이면 기존 청크를 바꾼다(재파싱)"""
        self._records[record.record_id] = record
        self._chunks[record.record_id] = tuple(chunks)

    async def search_chunks(
        self, query: ChunkSearchQuery
    ) -> tuple[RetrievedChunk, ...]:
        found = [
            _retrieved(record, chunk, _cosine(query.embedding, chunk.embedding))
            for record in self._records.values()
            if _matches(record, query)
            for chunk in self._chunks[record.record_id]
        ]
        found.sort(key=lambda chunk: chunk.score, reverse=True)
        return tuple(found[: query.limit])


def _matches(record: StoredRecord, query: ChunkSearchQuery) -> bool:
    # 동아리 범위는 필터와 달리 항상 적용한다
    if record.club_id != query.club_id:
        return False
    if query.category is not None and record.category != query.category:
        return False
    if query.event_id is not None and record.event_id != query.event_id:
        return False
    return True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """pgvector의 1 - (a <=> b)와 같은 값"""
    norm = math.hypot(*a) * math.hypot(*b)
    if norm == 0:
        return 0.0
    # 부동소수점 오차로 1을 살짝 넘으면 RetrievedChunk 검증에 걸린다
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b)) / norm))


def _retrieved(
    record: StoredRecord, chunk: IndexedChunk, score: float
) -> RetrievedChunk:
    return RetrievedChunk(
        text=chunk.text,
        source=RecordSource(
            record_id=record.record_id,
            file_name=record.file_name,
            location=chunk.location,
        ),
        category=record.category,
        event_id=record.event_id,
        score=score,
    )
