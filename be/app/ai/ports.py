"""
AI가 필요로 하는 BE 기능의 인터페이스를 정의한다.

AI는 BE의 내부 모듈로 동작하지만, BE 서비스·ORM·DB 세션에 직접 의존하지 않는다.
대신 이 파일에 정의된 인터페이스를 통해 필요한 기능을 요청하고,
실제 구현체는 BE에서 주입한다. 내부 HTTP 호출은 사용하지 않는다.

주로 다음과 같은 기능이 여기에 정의된다.

계산
참가비, 미납액, 환불액 등 정확성이 필요한 값은 BE가 계산한다.
AI는 계산 결과를 받아 판단에 사용하며 직접 값을 만들거나 보정하지 않는다.

기록 검색
저장된 청크 조회와 동아리 범위 제한은 BE가 한다.
AI는 질문 임베딩을 넘기고 비슷한 청크를 받는다.

필요한 인터페이스는 관련 기능과 정책이 확정되는 시점에
BE와 계약을 맞춘 뒤 추가한다.
"""

from typing import Protocol

from pydantic import Field

from app.core.enums import RecordCategory

from .contracts import ContractModel, RecordSource
from .llm import EMBEDDING_DIMENSIONS


class ChunkSearchQuery(ContractModel):
    """청크 검색 요청"""

    # BE는 이 동아리의 청크만 돌려준다
    club_id: str
    # 질문 임베딩. 청크와 같은 모델, 차원이어야 비교가능
    embedding: tuple[float, ...] = Field(
        min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS
    )
    limit: int = Field(ge=1) # 몇개를 받을지 정함
    category: RecordCategory | None = None
    # 행사와 연결된 기록(피드백 기록 등)만 볼 때 쓴다
    event_id: str | None = None


class RetrievedChunk(ContractModel):
    """검색된 청크 하나 (반환된)"""

    text: str
    # 답변의 출처로 그대로 옮긴다 (검색되지 않은 기록을 출처로 만들지 않기 위해서)
    source: RecordSource
    category: RecordCategory # 어떤 분류의 자료인지
    event_id: str | None = None
    # 코사인 유사도 -> 클수록 비슷
    score: float = Field(ge=-1, le=1)


class RecordSearchPort(Protocol):
    """기록 청크 검색. 구현체는 BE가 주입한다"""

    async def search_chunks(
        self, query: ChunkSearchQuery
    ) -> tuple[RetrievedChunk, ...]:
        """비슷한 청크를 유사도 높은 순서로 `limit`개 이하 돌려준다.

        결과가 없으면 빈 튜플이다. 기록이 없는 것은 실패가 아니다.
        """
        ...
