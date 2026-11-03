"""BE 회의 payload가 공개 경계에서 자료 답·없음·실패로 이어지는지 확인한다."""

import asyncio

import pytest

import app.ai
from app.ai.config import get_settings
from app.ai.errors import AIRetryableError
from app.ai.features.meeting import nodes
from app.ai.features.meeting.lookup import RecordsLookup
from app.ai.features.meeting.schemas import JudgeOutput
from app.ai.features.retrieval.schemas import EvidenceAssessment, EvidenceItem
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.core.enums import RecordCategory


@pytest.fixture(autouse=True)
def model_settings(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "test-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def payload():
    def utterance(seq, text):
        return {"utterance_id": f"u-{seq}", "seq": seq, "version": 2, "text": text,
                "started_at": "2026-10-19T10:00:00+09:00", "ended_at": "2026-10-19T10:00:01+09:00"}
    return {"meeting_id": "mtg-1", "club_id": "club-1",
            "utterance": utterance(5, "작년 숙소비 얼마였지?"),
            "context": [utterance(i, f"앞 발화 {i}") for i in range(1, 5)]}


class FakePort:
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error, self.queries = chunks, error, []

    async def search_chunks(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.chunks


def run(monkeypatch, port):
    async def judge(messages):
        return JudgeOutput(needs_lookup=True, query="작년 숙소비")

    async def embed(texts):
        return [(1.0,) + (0.0,) * (EMBEDDING_DIMENSIONS - 1) for _ in texts]

    async def assess(messages, schema):
        return EvidenceAssessment(sufficient=True, retry_queries=[],
            facts=[EvidenceItem(content="숙소비 550,000원", chunk_ids=["c1"])],
            not_found=[], conflicts=[])

    async def injected_judge(request, *, lookup, progress):
        return await nodes.judge_utterance(request, lookup=lookup, progress=progress, judge=judge)

    monkeypatch.setattr(app.ai.facade, "judge_meeting_utterance", injected_judge)
    monkeypatch.setattr(app.ai.facade, "RecordsLookup",
                        lambda records: RecordsLookup(records, embed=embed, invoke=assess))
    request = app.ai.JudgeUtteranceRequest.model_validate(payload())
    return asyncio.run(app.ai.judge_utterance(request, records=port))


def test_public_payload_returns_answer_with_searched_source(monkeypatch):
    source = app.ai.RecordSource(record_id="rec-1", file_name="결과보고.pdf",
                                 location=app.ai.SourceLocation(label="2쪽"))
    port = FakePort((app.ai.RetrievedChunk(text="숙소비 550,000원", source=source,
                                           category=RecordCategory.ETC, score=0.9),))
    result = run(monkeypatch, port)
    assert (result.utterance_id, result.source_version, result.kind) == ("u-5", 2, "ANSWER")
    assert (result.answer, result.sources) == ("숙소비 550,000원", (source,))
    assert port.queries[0].club_id == "club-1"


def test_public_payload_keeps_empty_and_failure_distinct(monkeypatch):
    assert run(monkeypatch, FakePort()).kind == "NOT_FOUND"
    with pytest.raises(AIRetryableError) as raised:
        run(monkeypatch, FakePort(error=AIRetryableError("검색 실패")))
    assert raised.value.trace.tool_calls[0].status == "FAILED"
