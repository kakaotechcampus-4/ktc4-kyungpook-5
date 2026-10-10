"""기록 색인 계약이 잘못된 값을 경계에서 막는지 검증한다."""

import pytest
from pydantic import ValidationError

from app.ai.contracts import (
    IndexedChunk,
    IndexRecordRequest,
    IndexRecordResult,
    RecordBlock,
    SourceLocation,
)
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.core.enums import RecordFileType

LOCATION = SourceLocation(label="예산 항목")
EMBEDDING = (0.0,) * EMBEDDING_DIMENSIONS


def _chunk(**overrides) -> IndexedChunk:
    values = {
        "text": "1인 회비 45,000원",
        "location": LOCATION,
        "block_indexes": (0,),
        "embedding": EMBEDDING,
    } | overrides
    return IndexedChunk(**values)


def test_공백뿐인_블록은_거부한다():
    with pytest.raises(ValidationError):
        RecordBlock(text="  \n", location=LOCATION)


def test_위치_이름이_비면_거부한다():
    with pytest.raises(ValidationError):
        SourceLocation(label=" ")


def test_블록이_없는_기록도_계약은_통과한다():
    """빈 기록은 계약이 막지 않고 index_record가 AIEmptyRecordError로 알린다."""
    request = IndexRecordRequest(
        record_id="rec_test",
        file_name="미분류 문서.pdf",
        file_type=RecordFileType.PDF,
        blocks=(),
    )

    assert request.blocks == ()


def test_파일_없는_텍스트_기록을_받는다():
    request = IndexRecordRequest(
        record_id="rec_test",
        file_name="2026 봄 MT 피드백",
        file_type=None,
        blocks=(RecordBlock(text="28명 참가", location=SourceLocation(label="회고")),),
    )

    assert request.file_type is None


def test_임베딩_차원이_다르면_거부한다():
    with pytest.raises(ValidationError):
        _chunk(embedding=(0.0,) * (EMBEDDING_DIMENSIONS - 1))


@pytest.mark.parametrize("block_indexes", [(), (-1,)])
def test_원본_블록_번호가_없거나_음수면_거부한다(block_indexes):
    with pytest.raises(ValidationError):
        _chunk(block_indexes=block_indexes)


def test_청크가_없는_결과는_거부한다():
    with pytest.raises(ValidationError):
        IndexRecordResult(chunks=())


def test_청크가_있으면_결과를_만든다():
    result = IndexRecordResult(chunks=(_chunk(),))

    assert len(result.chunks) == 1
