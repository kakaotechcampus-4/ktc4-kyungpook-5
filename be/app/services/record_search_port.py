"""app.ai.RecordSearchPort의 실제(DB 기반) 구현 (#141).

임베딩 자체(질의문 → 벡터)는 AI 쪽 RecordsLookup이 계산해 ChunkSearchQuery.embedding에
담아 넘긴다. 여기서는 pgvector로 코사인 유사도 검색만 한다.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import ChunkSearchQuery, RecordSource, RetrievedChunk, SourceLocation
from app.models.records import RecordChunk


class DbRecordSearchPort:
    """동아리 범위로 기록 청크를 검색한다. 요청 하나(judge_utterance 호출 하나)마다
    새로 만든다 — 세션 수명을 그 호출 범위로 제한하기 위해서다."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_chunks(
        self, query: ChunkSearchQuery
    ) -> tuple[RetrievedChunk, ...]:
        distance = RecordChunk.embedding.cosine_distance(list(query.embedding))
        conditions = [RecordChunk.club_id == query.club_id]
        if query.category is not None:
            conditions.append(RecordChunk.category == query.category)
        if query.event_id is not None:
            conditions.append(RecordChunk.event_id == query.event_id)

        rows = await self._session.execute(
            select(RecordChunk, distance.label("distance"))
            .where(*conditions)
            .order_by(distance)
            .limit(query.limit)
        )
        return tuple(
            RetrievedChunk(
                text=chunk.text,
                source=RecordSource(
                    record_id=chunk.record_id,
                    file_name=chunk.file_name,
                    location=SourceLocation(label=chunk.location_label),
                ),
                category=chunk.category,
                event_id=chunk.event_id,
                # pgvector의 <=> 는 코사인 거리다. 유사도 점수는 1 - 거리.
                score=max(-1.0, min(1.0, 1 - distance_value)),
            )
            for chunk, distance_value in rows.all()
        )
