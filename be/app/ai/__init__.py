"""BE 내부 AI 모듈의 단일 공개 진입점.

공개 기능은 facade, 데이터는 contracts, 주입 계약은 ports에 정의한 뒤
여기서 명시적으로 재공개한다. BE는 여기 있는 이름만 사용한다.
enum은 재공개하지 않는다. `app.core.enums`에서 가져온다.
"""

from .contracts import (
    IndexedChunk,
    IndexRecordRequest,
    IndexRecordResult,
    RecordBlock,
    RecordSource,
    SourceLocation,
)
from .facade import index_record
from .llm import EMBEDDING_DIMENSIONS
from .ports import ChunkSearchQuery, RecordSearchPort, RetrievedChunk

__all__ = (
    # 기록 색인
    "index_record",
    "IndexRecordRequest",
    "IndexRecordResult",
    "IndexedChunk",
    "RecordBlock",
    "SourceLocation",
    # 기록 검색 port (BE가 구현)
    "RecordSearchPort",
    "ChunkSearchQuery",
    "RetrievedChunk",
    "RecordSource",
    # 청크 벡터 컬럼 차원
    "EMBEDDING_DIMENSIONS",
)
