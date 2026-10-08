"""기록 검색 port의 데이터가 잘못된 값을 경계에서 막는지 검증한다."""

import pytest
from pydantic import ValidationError

from app.ai.contracts import RecordSource, SourceLocation
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.ai.ports import ChunkSearchQuery, RetrievedChunk
from app.core.enums import RecordCategory

EMBEDDING = (0.0,) * EMBEDDING_DIMENSIONS
SOURCE = RecordSource(
    record_id="rec_test",
    file_name="2025 봄 MT 결과보고.pdf",
    location=SourceLocation(label="예산 항목"),
)


def test_필터_없이_검색할_수_있다():
    query = ChunkSearchQuery(club_id="clb_test", embedding=EMBEDDING, limit=5)

    assert query.category is None
    assert query.event_id is None


def test_질문_임베딩_차원이_다르면_거부한다():
    with pytest.raises(ValidationError):
        ChunkSearchQuery(club_id="clb_test", embedding=(0.0,) * 3, limit=5)


def test_조회_개수가_0이면_거부한다():
    with pytest.raises(ValidationError):
        ChunkSearchQuery(club_id="clb_test", embedding=EMBEDDING, limit=0)


@pytest.mark.parametrize("score", [-1.5, 1.5])
def test_유사도_범위를_벗어나면_거부한다(score):
    """거리 값을 유사도로 잘못 넘기는 경우를 잡는다."""
    with pytest.raises(ValidationError):
        RetrievedChunk(
            text="1인 회비 45,000원",
            source=SOURCE,
            category=RecordCategory.ETC,
            score=score,
        )
