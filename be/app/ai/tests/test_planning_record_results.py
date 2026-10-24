"""참고 결과의 상태 일관성·출처 보존·충돌만 존재하는 경우를 검증한다."""

import pytest
from pydantic import ValidationError

from app.ai.features.planning.records import build_planning_record_result
from app.ai.features.planning.schemas import PlanningRecordSearchInput, PlanningRecordSearchResult
from app.ai.features.retrieval.schemas import RecordSearchResult


def fact(content, record_id):
    return {"content": content, "sources": [{
        "record_id": record_id, "file_name": f"{record_id}.pdf",
        "location": {"label": "2쪽 · 장소"},
    }]}


CONFLICT = {"description": "장소 기록이 다름", "values": [fact("가평", "r1"), fact("춘천", "r2")]}
IDS = {"planning_event_id": "current", "request_id": "turn-9", "base_version": 7}


@pytest.mark.parametrize("payload,status", [
    ({"facts": [fact("가평", "r1")]}, "AVAILABLE"),
    ({"conflicts": [CONFLICT]}, "AVAILABLE"),
    ({"conflicts": [CONFLICT], "not_found": ["교통비"]}, "AVAILABLE"),
    ({"facts": [fact("1박 2일", "r3")], "conflicts": [CONFLICT], "not_found": ["교통비"]}, "AVAILABLE"),
    ({"not_found": ["장소", "교통비"]}, "NOT_FOUND"),
])
def test_lossless_conversion_and_serialization(payload, status):
    request = PlanningRecordSearchInput.model_validate({
        **IDS, "club_id": "club", "query": "작년 MT", "reference_date": "2026-10-23",
        "conditions": {"headcount": 40, "location": "올해 장소"},
    })
    source = RecordSearchResult.model_validate(payload)
    before = (request.model_dump(), source.model_dump())
    result = build_planning_record_result(request, source)
    assert result.status == status
    assert result.model_dump(include=set(IDS)) == IDS
    assert result.cards == source.facts
    assert result.conflicts == source.conflicts
    assert result.not_found == source.not_found
    assert PlanningRecordSearchResult.model_validate_json(result.model_dump_json()) == result
    assert (request.model_dump(), source.model_dump()) == before


@pytest.mark.parametrize("payload", [
    {"status": "AVAILABLE"},
    {"status": "AVAILABLE", "not_found": ["장소"]},
    {"status": "NOT_FOUND"},
    {"status": "NOT_FOUND", "cards": [fact("가평", "r1")], "not_found": ["교통비"]},
    {"status": "NOT_FOUND", "conflicts": [CONFLICT], "not_found": ["교통비"]},
    {"status": "AVAILABLE", "cards": [{"content": "가평", "sources": []}]},
    {"status": "NOT_FOUND", "not_found": [" "]},
])
def test_invalid_status_or_missing_evidence_is_rejected(payload):
    with pytest.raises(ValidationError):
        PlanningRecordSearchResult.model_validate({**IDS, **payload})
