"""회의 발화 판단이 모델 출력으로 결과를 구성하는지 확인한다.

모델 대신 정해진 판단을 돌려주는 가짜 함수를, 기록 검색 대신 가짜 RecordLookup을 쓴다.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.ai.config import get_settings
from app.ai.contracts import RecordSource, SourceLocation
from app.ai.errors import AIInvalidResponseError, AIRetryableError, AITimeoutError
from app.ai.features.meeting import nodes
from app.ai.features.meeting.context import PROMPT_VERSION
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.schemas import (
    JudgeOutput,
    JudgeUtteranceRequest,
    MeetingAnswer,
    MeetingUtterance,
)
from app.ai.ports import RetrievedChunk
from app.core.enums import RecordCategory

MODEL = "gpt-5.6-luna"
CLUB = "clb_keunnamu"
AT = datetime(2026, 3, 5, 5, 0, tzinfo=timezone.utc)

FOUND = RecordSource(
    record_id="rec_mt_2025", file_name="2025 봄 MT 결과보고", location=SourceLocation(label="2쪽 · 2. 예산")
)
OTHER = RecordSource(record_id="rec_rules", file_name="동아리 회칙", location=SourceLocation(label="2쪽"))
CHUNK = RetrievedChunk(text="숙소비 550,000원", source=FOUND, category=RecordCategory.EVENT_HISTORY, score=0.82)


@pytest.fixture(autouse=True)
def _model_name(monkeypatch):
    """trace.model은 AI_MODEL 설정값이다"""
    monkeypatch.setenv("AI_MODEL", MODEL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _request(text="그때 숙소비 얼마였지?", version=1):
    return JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id=CLUB,
        utterance=MeetingUtterance(
            utterance_id="u-31", seq=31, version=version, text=text, started_at=AT, ended_at=AT
        ),
    )


def _judge(needs_lookup, query=""):
    calls = []

    async def judge(messages):
        calls.append(messages)
        return JudgeOutput(needs_lookup=needs_lookup, query=query)

    judge.calls = calls
    return judge


class FakeLookup:
    def __init__(self, chunks=(), answer=None):
        self.chunks = chunks
        self.result = answer
        self.searched = []

    async def search(self, club_id, question):
        self.searched.append((club_id, question))
        return self.chunks

    async def answer(self, question, chunks):
        return self.result


class Progress:
    def __init__(self):
        self.stages = []

    async def stage_changed(self, utterance_id, stage):
        self.stages.append((utterance_id, stage))


def _run(request, judge, lookup=None, progress=None):
    return asyncio.run(
        judge_utterance(request, lookup=lookup or FakeLookup(), progress=progress, judge=judge)
    )


def test_조회가_필요_없으면_NONE이고_도구를_부르지_않는다():
    lookup, progress = FakeLookup(), Progress()

    result = _run(_request("민수야 예약했어?"), _judge(False), lookup, progress)

    assert (result.route, result.kind, result.question) == ("NONE", "NO_LOOKUP", None)
    assert result.trace.tool_calls == ()
    assert lookup.searched == []
    assert progress.stages == [("u-31", "JUDGING")]


def test_조회가_필요_없다는_판단의_검색어는_버린다():
    result = _run(_request(), _judge(False, "2025 봄 MT 숙소비"))

    assert result.route == "NONE"
    assert result.question is None


def test_답을_찾으면_ANSWER와_출처를_돌려준다():
    lookup = FakeLookup((CHUNK,), MeetingAnswer(answer="550,000원", sources=(FOUND,)))
    progress = Progress()

    result = _run(_request(), _judge(True, "2025 봄 MT 숙소비"), lookup, progress)

    assert (result.route, result.kind) == ("RAG", "ANSWER")
    assert result.question == "2025 봄 MT 숙소비"
    assert (result.answer, result.sources) == ("550,000원", (FOUND,))
    assert lookup.searched == [(CLUB, "2025 봄 MT 숙소비")]
    assert [stage for _, stage in progress.stages] == ["JUDGING", "SEARCHING", "ANSWERING"]
    assert [call.tool for call in result.trace.tool_calls] == ["records.search", "llm.generate"]
    assert result.trace.tool_calls[0].result_count == 1


def test_검색_결과가_없으면_답을_쓰지_않고_NOT_FOUND다():
    progress = Progress()

    result = _run(_request(), _judge(True, "2024 신환회 장소"), FakeLookup(), progress)

    assert (result.route, result.kind, result.question) == ("RAG", "NOT_FOUND", "2024 신환회 장소")
    assert [stage for _, stage in progress.stages] == ["JUDGING", "SEARCHING"]
    assert [(call.tool, call.result_count) for call in result.trace.tool_calls] == [("records.search", 0)]


def test_찾은_조각에_답이_없으면_NOT_FOUND다():
    result = _run(_request(), _judge(True, "2025 봄 MT 숙소비"), FakeLookup((CHUNK,), None))

    assert result.kind == "NOT_FOUND"
    assert [call.tool for call in result.trace.tool_calls] == ["records.search", "llm.generate"]


def test_검색되지_않은_기록을_출처로_내보내지_않는다():
    lookup = FakeLookup((CHUNK,), MeetingAnswer(answer="20,000원", sources=(OTHER,)))

    with pytest.raises(AIInvalidResponseError, match="출처"):
        _run(_request(), _judge(True, "2025 봄 MT 숙소비"), lookup)


@pytest.mark.parametrize("query", ["", "   "])
def test_조회가_필요한데_검색어가_없으면_오류다(query):
    # NONE으로 바꾸면 놓친 질문이 기록에 남지 않는다
    with pytest.raises(AIInvalidResponseError):
        _run(_request(), _judge(True, query))


def test_검색어_앞뒤_공백은_뺀다():
    result = _run(_request(), _judge(True, "  2025 봄 MT 숙소비 "))

    assert result.question == "2025 봄 MT 숙소비"


def test_판단_기록은_코드가_채운다():
    result = _run(_request(version=3), _judge(False))

    assert result.utterance_id == "u-31"
    assert result.source_version == 3
    assert (result.trace.model, result.trace.prompt_version) == (MODEL, PROMPT_VERSION)
    assert result.trace.judge_ms >= 0


def test_같은_요청을_다시_보내도_다시_판단한다():
    # 중복 억제를 하지 않는다(AI-MEET-04)
    judge = _judge(True, "2025 봄 MT 숙소비")
    lookup = FakeLookup()

    first = _run(_request(), judge, lookup)
    second = _run(_request(), judge, lookup)

    assert len(judge.calls) == 2
    assert len(lookup.searched) == 2
    assert first.kind == second.kind == "NOT_FOUND"


def test_판단이_제한_시간을_넘기면_시간_초과_오류다(monkeypatch):
    monkeypatch.setattr(nodes, "JUDGE_TIMEOUT_SECONDS", 0.01)

    async def slow(messages):
        await asyncio.sleep(1)

    with pytest.raises(AITimeoutError):
        _run(_request(), slow)


def test_모델_오류는_NONE으로_바꾸지_않고_그대로_올린다():
    async def failing(messages):
        raise AIRetryableError("모델 API에 연결하지 못했습니다")

    with pytest.raises(AIRetryableError):
        _run(_request(), failing)


def test_검색_오류는_NOT_FOUND로_바꾸지_않고_그대로_올린다():
    class FailingLookup(FakeLookup):
        async def search(self, club_id, question):
            raise AIRetryableError("임베딩 호출 실패")

    with pytest.raises(AIRetryableError):
        _run(_request(), _judge(True, "2025 봄 MT 숙소비"), FailingLookup())


def test_진행_알림을_넘기지_않아도_판단한다():
    result = _run(_request(), _judge(False), progress=None)

    assert result.kind == "NO_LOOKUP"
