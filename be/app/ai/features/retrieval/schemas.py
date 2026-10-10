"""기록 검색·근거 구성에 필요한 기능 전용 데이터 형식을 정의한다."""

from typing import Annotated

from pydantic import Field

from ...contracts import ContractModel, NonBlankStr, SourceLocation


class TextChunk(ContractModel):
    """임베딩하기 전의 청크. 임베딩을 붙이면 계약의 `IndexedChunk`가 된다"""

    text: NonBlankStr
    location: SourceLocation
    block_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)
