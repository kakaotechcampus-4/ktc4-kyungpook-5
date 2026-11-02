"""P1 검색 상세와 옛 응답이 제품 경계에서 손실·오해되지 않도록 검증한다."""

import app.ai as ai
from app.schemas.events import PlanScreenOut, RecordLookupOut
from app.services.planning_service import _record_lookup_out


def test_evidence_is_camel_case_and_contains_only_public_facts_and_sources():
    source = ai.RecordSource(record_id="record-1", file_name="MT 장부.xlsx",
                             location=ai.SourceLocation(label="수입 · 2행"))
    fact = ai.RecordFact(content="2025 봄 MT 참가비 45000원", sources=(source,))
    lookup = ai.RecordLookupResult(status="available", query="2025 봄 MT 참가비",
        result=ai.RecordSearchResult(facts=(fact,), not_found=("식비 세부 내역",),
            conflicts=(ai.RecordConflict(description="숙소비",
                values=(fact, fact.model_copy(update={"content": "다른 자료의 금액"}))),)))
    data = RecordLookupOut.model_validate(_record_lookup_out(lookup)).model_dump(by_alias=True)
    assert data["result"]["facts"][0]["sources"] == [{
        "recordId": "record-1", "fileName": "MT 장부.xlsx", "location": {"label": "수입 · 2행"},
    }]
    assert data["result"]["notFound"] == ["식비 세부 내역"]
    assert len(data["result"]["conflicts"][0]["values"]) == 2
    assert set(data) == {"status", "query", "reason", "result"}
    assert set(data["result"]) == {"facts", "notFound", "conflicts"}
    assert _record_lookup_out(None) is None


def test_old_lookup_without_detail_is_not_relabelled_as_not_found():
    old = RecordLookupOut.model_validate({"status": "available", "query": "옛 조회", "reason": None})
    assert old.status == "available"
    assert old.result is None
    assert not PlanScreenOut.model_fields["last_record_lookup"].is_required()
