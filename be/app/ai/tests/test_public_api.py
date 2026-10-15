"""BE가 app.ai에서 가져다 쓰는 공개 이름을 검증한다."""

import asyncio

import pytest

import app.ai
from app.ai import AIEmptyRecordError, IndexRecordRequest, index_record
from app.ai.features.meeting.lookup import RecordsLookup
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch


def test_공개_목록의_이름을_모두_가져올_수_있다():
    for name in app.ai.__all__:
        assert hasattr(app.ai, name), name


def test_빈_기록은_빈_결과_대신_AIEmptyRecordError로_알린다():
    request = IndexRecordRequest(
        record_id="rec_test", file_name="빈 장부.csv", file_type="CSV", blocks=()
    )

    with pytest.raises(AIEmptyRecordError):
        asyncio.run(index_record(request))



def test_회의_판단은_BE가_넘긴_검색_port로_기록을_찾는다(monkeypatch):
    calls = []

    async def fake_judge(request, *, lookup, progress):
        calls.append((request, lookup, progress))
        return "결과"

    monkeypatch.setattr(app.ai.facade, "judge_meeting_utterance", fake_judge)
    records, progress = InMemoryRecordSearch(), object()

    result = asyncio.run(app.ai.judge_utterance("요청", records=records, progress=progress))

    [(request, lookup, given_progress)] = calls
    assert (result, request, given_progress) == ("결과", "요청", progress)
    # BE는 port만 넘기고, 검색과 답 작성을 잇는 일은 AI가 한다
    assert isinstance(lookup, RecordsLookup)
    assert lookup._records is records
