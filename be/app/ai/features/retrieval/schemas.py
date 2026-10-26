"""기록 검색·근거 구성에 필요한 기능 전용 데이터 형식을 정의한다."""

from ...contracts import RecordFact, RecordConflict, RecordSearchResult

from datetime import date
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field, model_validator

from app.core.enums import RecordCategory

from ...contracts import (
    ContractModel,
    EventConditions,
    NonBlankStr,
    RecordSource,
    SourceLocation,
)
from ...ports import RetrievedChunk


class TextChunk(ContractModel):
    """임베딩하기 전의 청크. 임베딩을 붙이면 계약의 `IndexedChunk`가 된다"""

    text: NonBlankStr
    location: SourceLocation
    block_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)


# --- 기록 검색 (search_records) -----------------------------------------------


class RecordSearchRequest(ContractModel):
    """기록 검색 입력. planning·operations·회의 어시스턴트와 Agent Tool이 같은 형식으로 부른다"""

    # 이 동아리의 기록만 찾는다. 범위 제한은 port 구현체(BE)가 보장한다
    club_id: str
    # 찾을 내용. 예: "작년 MT 회비"
    query: NonBlankStr
    # "작년"·"지난 학기"를 연도로 바꾸는 기준일. 호출하는 쪽이 오늘 날짜를 넘긴다
    today: date
    # 계획 중인 행사. 행사 종류·시기로 검색어를 구체화한다
    conditions: EventConditions | None = None
    category: RecordCategory | None = None
    event_id: str | None = None
    # 검색어 하나당 받을 청크 수
    limit: int = Field(default=5, ge=1)


# LLM 출력 형식. 출처는 모델이 쓰지 않고 자료 id(c1, c2…)로만 가리키게 해서
# 코드가 검색된 청크의 출처로 바꾼다. 검색되지 않은 기록이 출처로 나갈 수 없다.


class SearchQueries(BaseModel):
    """검색어 정리 결과"""

    queries: list[str] = Field(min_length=1)


class EvidenceItem(BaseModel):
    content: str
    chunk_ids: list[str]


class EvidenceConflict(BaseModel):
    description: str
    values: list[EvidenceItem]


class EvidenceAssessment(BaseModel):
    """근거가 충분한지 판단하고 지금 자료로 결과를 구성한 것"""

    sufficient: bool
    # 부족할 때 다시 찾을 검색어
    retry_queries: list[str]
    facts: list[EvidenceItem]
    not_found: list[str]
    conflicts: list[EvidenceConflict]


class SearchState(TypedDict):
    """검색 처리 단계가 주고받는 상태. 각 단계는 바뀐 값만 돌려준다"""

    request: RecordSearchRequest
    # 다음 검색에 쓸 검색어
    queries: list[str]
    # 이미 찾은 검색어. 같은 검색어로 다시 찾지 않는다
    searched: list[str]
    # 지금까지 찾은 청크. 순서가 자료 id(c1부터)라 회차가 바뀌어도 앞 번호가 유지된다
    chunks: list[RetrievedChunk]
    rounds: int
    assessment: EvidenceAssessment | None
    result: RecordSearchResult | None
