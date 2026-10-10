"""BE가 app.ai에서 가져다 쓰는 공개 이름을 검증한다."""

import asyncio

import pytest

import app.ai
from app.ai import AIEmptyRecordError, IndexRecordRequest, index_record


def test_공개_목록의_이름을_모두_가져올_수_있다():
    for name in app.ai.__all__:
        assert hasattr(app.ai, name), name


def test_빈_기록은_빈_결과_대신_AIEmptyRecordError로_알린다():
    request = IndexRecordRequest(
        record_id="rec_test", file_name="빈 장부.csv", file_type="CSV", blocks=()
    )

    with pytest.raises(AIEmptyRecordError):
        asyncio.run(index_record(request))

