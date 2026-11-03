"""토리 자료 답변의 공개 응답 계약."""

import pytest
from pydantic import ValidationError

from app.schemas.common import Envelope
from app.schemas.tori import ToriMessageOut

META = {"semanticStatus": "AVAILABLE", "unindexedCount": 0, "searchedChunkCount": 1, "candidateLimit": 50, "candidateLimitReached": False, "lexicalChunkCount": 0, "lexicalOmitted": False, "filenameOnlyUnanalyzedCount": 0}


def test_record_answer_has_per_fact_camel_case_sources():
    response = Envelope(data=ToriMessageOut(
        intent="record_search",
        reply="자료에서 확인한 내용이에요.",
        record_answer={
            "status": "answered", **META,
            "facts": [{
                "text": "장소 대여비는 30만 원이에요.",
                "sources": [{"record_id": "rec_1", "file_name": "예산.csv", "location": {"label": "2행"}}],
            }],
        },
    )).model_dump(mode="json", by_alias=True)
    assert response["data"]["recordAnswer"] == {
        "status": "answered", **META,
        "conflicts": [],
        "notFound": [],
        "facts": [{"text": "장소 대여비는 30만 원이에요.", "sources": [
            {"recordId": "rec_1", "fileName": "예산.csv", "location": {"label": "2행"}}
        ]}],
    }
    assert response["data"]["records"] is None


def test_facts_require_sources_and_existing_responses_remain_valid():
    with pytest.raises(ValidationError):
        ToriMessageOut(intent="record_search", reply="답", record_answer={
            "status": "answered", **META, "facts": [{"text": "출처 없는 답", "sources": []}],
        })
    existing = ToriMessageOut(intent="meeting", reply="회의 화면으로 이동해요.", navigation="/meetings")
    assert existing.record_answer is None
    assert existing.navigation == "/meetings"


@pytest.mark.parametrize("status", ["answered", "partial", "insufficient", "failed"])
def test_all_agreed_statuses_are_serialized(status):
    answer = ToriMessageOut(intent="record_search", reply="안내", record_answer={"status": status, **META})
    assert answer.model_dump(by_alias=True)["recordAnswer"]["status"] == status


def test_conflicts_and_unknowns_keep_each_source():
    source = {"recordId": "rec_1", "fileName": "예산.csv", "location": {"label": "2행"}}
    answer = ToriMessageOut(intent="record_search", reply="차이가 있어요.", record_answer={
        "status": "partial", **META, "conflicts": [{"description": "예산 차이", "values": [
            {"text": "30만 원", "sources": [source]}, {"text": "40만 원", "sources": [source]},
        ]}], "not_found": ["최종 승인 여부"],
    }).model_dump(by_alias=True)["recordAnswer"]
    assert answer["conflicts"][0]["values"][0]["sources"][0] == source
    assert answer["notFound"] == ["최종 승인 여부"]
