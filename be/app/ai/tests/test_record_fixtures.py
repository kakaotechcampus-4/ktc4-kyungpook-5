"""예시 기록이 parse_result 형식과 색인 계약에 맞는지 검증한다."""

import json
from pathlib import Path

import pytest

from app.ai.contracts import IndexRecordRequest
from app.core.enums import RecordCategory

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "records").glob("*.json"))


def test_예시_기록은_4종이다():
    assert len(FIXTURES) == 4


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_예시_기록으로_색인_요청을_만들_수_있다(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    record = data["record"]

    request = IndexRecordRequest(
        record_id=record["id"],
        file_name=record["file_name"],
        file_type=record["file_type"],
        blocks=data["parse_result"]["blocks"],
    )

    assert request.blocks
    RecordCategory(record["category"])
