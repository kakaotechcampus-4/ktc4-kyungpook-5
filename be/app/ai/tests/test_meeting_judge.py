"""회의 발화 판단이 판단 모델의 확률과 검색어로 결과를 구성하는지 확인한다.

Jev 대신 정해진 확률을, luna 대신 정해진 검색어를 돌려주는 가짜 함수를 쓰고,
기록 검색 대신 가짜 RecordLookup을 쓴다.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from app.ai.contracts import RecordSource, SourceLocation
from app.ai.errors import AIInvalidResponseError, AIRetryableError, AITimeoutError
from app.ai.features.meeting import nodes
from app.ai.features.meeting.context import (
    JEV_MODEL,
    JEV_THRESHOLD,
    QUERY_PROMPT_VERSION,
    build_judge_input,
)
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.questions import QUESTIONS_VERSION
from app.ai.features.meeting.schemas import (
    JudgeUtteranceRequest,
    MeetingAnswer,
    MeetingUtterance,
    QueryOutput,
)
from app.ai.ports import RetrievedChunk
from app.core.enums import RecordCategory

CLUB = "clb_keunnamu"
AT = datetime(2026, 3, 5, 5, 0, tzinfo=timezone.utc)

FOUND = RecordSource(
    record_id="rec_mt_2025", file_name="2025 봄 MT 결과보고", location=SourceLocation(label="2쪽 · 2. 예산")
)
OTHER = RecordSource(record_id="rec_rules", file_name="동아리 회칙", location=SourceLocation(label="2쪽"))
CHUNK = RetrievedChunk(text="숙소비 550,000원", source=FOUND, category=RecordCategory.EVENT_HISTORY, score=0.82)


def _request(text="그때 숙소비 얼마였지?", version=1):
    return JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id=CLUB,
        utterance=MeetingUtterance(
            utterance_id="u-31", seq=31, version=version, text=text, started_at=AT, ended_at=AT
        ),
    )


class FakeJudge:
    """Jev 대신 정해진 확률을, luna 대신 정해진 검색어를 돌려준다. 받은 입력을 남긴다"""

    def __init__(self, probability, query=""):
        self.probability = probability
        self.query_text = query
        self.states = []
        self.query_calls = []

    async def decide(self, state):
        self.states.append(state)
        return self.probability

    async def query(self, messages):
        self.query_calls.append(messages)
        return QueryOutput(query=self.query_text)


def _judge(needs_lookup, query=""):
    """조회면 임계값보다 높은 확률, 아니면 낮은 확률을 낸다"""
    return FakeJudge(0.83 if needs_lookup else 0.04, query)


class FakeLookup:
    answer_prompt_version = "test-answer-v1"

    def __init__(self, chunks=(), answer=None):
        self.chunks = chunks
        self.result = answer
        self.searched = []
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        self.searched.append((request.club_id, request.query))
        return self.chunks

    async def answer(self, request, chunks):
        return self.result


class Progress:
    def __init__(self):
        self.stages = []

    async def stage_changed(self, utterance_id, stage):
        self.stages.append((utterance_id, stage))


def _run(request, judge, lookup=None, progress=None):
    return asyncio.run(
        judge_utterance(
            request,
            lookup=lookup or FakeLookup(),
            progress=progress,
            decide=judge.decide,
            query=judge.query,
        )
    )


def test_조회가_필요_없으면_NONE이고_luna와_도구를_부르지_않는다():
    judge, lookup, progress = _judge(False), FakeLookup(), Progress()

    result = _run(_request("민수야 예약했어?"), judge, lookup, progress)

    assert (result.route, result.kind, result.question) == ("NONE", "NO_LOOKUP", None)
    # 남는 것은 Jev 판단 한 줄이다. 확률을 함께 남긴다
    [decided] = result.trace.tool_calls
    assert (decided.tool, decided.input, decided.status, decided.probability) == (
        "judge.decide",
        "민수야 예약했어?",
        "OK",
        0.04,
    )
    assert judge.query_calls == []
    assert lookup.searched == []
    assert progress.stages == [("u-31", "JUDGING")]


def test_Jev에는_판단_입력_글을_보낸다():
    request = _request()
    judge = _judge(False)

    _run(request, judge)

    assert judge.states == [build_judge_input(request)]


@pytest.mark.parametrize(
    ("probability", "route"),
    [(JEV_THRESHOLD, "RAG"), (round(JEV_THRESHOLD - 0.01, 2), "NONE"), (1.0, "RAG"), (0.0, "NONE")],
)
def test_확률이_임계값_이상이면_조회다(probability, route):
    # Jev는 확률을 0.01 단위로 준다. 0.35는 조회, 0.34는 아님이다
    result = _run(_request(), FakeJudge(probability, "2025 봄 MT 숙소비"))

    assert result.route == route


def test_답을_찾으면_ANSWER와_출처를_돌려준다():
    lookup = FakeLookup((CHUNK,), MeetingAnswer(answer="550,000원", sources=(FOUND,)))
    progress = Progress()

    result = _run(_request(), _judge(True, "2025 봄 MT 숙소비"), lookup, progress)

    assert (result.route, result.kind) == ("RAG", "ANSWER")
    assert result.question == "2025 봄 MT 숙소비"
    assert (result.answer, result.sources) == ("550,000원", (FOUND,))
    assert lookup.searched == [(CLUB, "2025 봄 MT 숙소비")]
    assert [stage for _, stage in progress.stages] == ["JUDGING", "SEARCHING", "ANSWERING"]
    # 판단 → 검색어(luna) → 기록 검색 → 답 작성 순서로 남는다
    calls = result.trace.tool_calls
    assert [(call.tool, call.prompt_version) for call in calls] == [
        ("judge.decide", None),
        ("llm.generate", QUERY_PROMPT_VERSION),
        ("records.search", None),
        ("llm.generate", "test-answer-v1"),
    ]
    assert calls[0].probability == 0.83
    assert calls[1].input == "그때 숙소비 얼마였지?"
    assert calls[2].result_count == 1


def test_기록_검색의_기준일은_한국_시간의_회의_날짜다():
    request = _request().model_copy(
        update={
            "utterance": _request().utterance.model_copy(
                # 한국 시간으로는 3월 5일 새벽 1시다
                update={"started_at": datetime(2026, 3, 4, 16, 0, tzinfo=timezone.utc)}
            )
        }
    )
    lookup = FakeLookup((CHUNK,), MeetingAnswer(answer="550,000원", sources=(FOUND,)))

    _run(request, _judge(True, "2025 봄 MT 숙소비"), lookup)

    [search] = lookup.requests
    assert (search.query, search.today.isoformat()) == ("2025 봄 MT 숙소비", "2026-03-05")


def test_검색_결과가_없으면_답을_쓰지_않고_NOT_FOUND다():
    progress = Progress()

    result = _run(_request(), _judge(True, "2024 신환회 장소"), FakeLookup(), progress)

    assert (result.route, result.kind, result.question) == ("RAG", "NOT_FOUND", "2024 신환회 장소")
    assert [stage for _, stage in progress.stages] == ["JUDGING", "SEARCHING"]
    assert [(call.tool, call.result_count) for call in result.trace.tool_calls] == [
        ("judge.decide", None),
        ("llm.generate", None),
        ("records.search", 0),
    ]


def test_찾은_조각에_답이_없으면_NOT_FOUND다():
    result = _run(_request(), _judge(True, "2025 봄 MT 숙소비"), FakeLookup((CHUNK,), None))

    assert result.kind == "NOT_FOUND"
    assert [call.tool for call in result.trace.tool_calls] == [
        "judge.decide",
        "llm.generate",
        "records.search",
        "llm.generate",
    ]


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
    # 모델 버전과 질문 문구 버전은 설정이 아니라 코드에 고정한 값이다
    assert (result.trace.model, result.trace.prompt_version) == (JEV_MODEL, QUESTIONS_VERSION)
    assert result.trace.judge_ms >= 0


def test_같은_요청을_다시_보내도_다시_판단한다():
    # 중복 억제를 하지 않는다(AI-MEET-04)
    judge = _judge(True, "2025 봄 MT 숙소비")
    lookup = FakeLookup()

    first = _run(_request(), judge, lookup)
    second = _run(_request(), judge, lookup)

    assert len(judge.states) == 2
    assert len(judge.query_calls) == 2
    assert len(lookup.searched) == 2
    assert first.kind == second.kind == "NOT_FOUND"


def test_판단이_제한_시간을_넘기면_시간_초과_오류다(monkeypatch):
    monkeypatch.setattr(nodes, "JUDGE_TIMEOUT_SECONDS", 0.01)

    class Slow(FakeJudge):
        async def decide(self, state):
            await asyncio.sleep(1)

    with pytest.raises(AITimeoutError) as caught:
        _run(_request(), Slow(0.9))

    # 실패한 판단도 판단 기록에 남는다(#117). Jev 응답을 받기 전에 끊겼다
    trace = caught.value.trace
    assert (trace.model, trace.prompt_version) == (JEV_MODEL, QUESTIONS_VERSION)
    assert trace.judge_ms >= 10
    assert trace.tool_calls == ()


def test_검색어_호출까지_제한_시간_안에_끝나야_한다(monkeypatch):
    # 제한 시간은 Jev 판단과 검색어 호출을 합친 판단 단계 전체에 건다
    monkeypatch.setattr(nodes, "JUDGE_TIMEOUT_SECONDS", 0.05)

    class SlowQuery(FakeJudge):
        async def query(self, messages):
            await asyncio.sleep(1)

    with pytest.raises(AITimeoutError) as caught:
        _run(_request(), SlowQuery(0.9, "2025 봄 MT 숙소비"))

    assert [call.tool for call in caught.value.trace.tool_calls] == ["judge.decide"]


def test_Jev_오류는_NONE으로_바꾸지_않고_그대로_올린다():
    class Failing(FakeJudge):
        async def decide(self, state):
            raise AIRetryableError("Jev API에 연결하지 못했습니다")

    judge = Failing(0.9)
    with pytest.raises(AIRetryableError) as caught:
        _run(_request(), judge)

    [decided] = caught.value.trace.tool_calls
    assert (decided.tool, decided.status, decided.probability) == ("judge.decide", "FAILED", None)
    # luna로 대신 판단하지 않는다
    assert judge.query_calls == []


def test_검색어_호출_오류는_판단과_실패한_호출을_남긴다():
    class Failing(FakeJudge):
        async def query(self, messages):
            raise AITimeoutError("모델 응답이 제한 시간 안에 오지 않았습니다")

    with pytest.raises(AITimeoutError) as caught:
        _run(_request(), Failing(0.9))

    assert [(call.tool, call.status) for call in caught.value.trace.tool_calls] == [
        ("judge.decide", "OK"),
        ("llm.generate", "TIMEOUT"),
    ]


def test_검색어_없는_조회_판단도_판단_기록을_남긴다():
    with pytest.raises(AIInvalidResponseError) as caught:
        _run(_request(), _judge(True, ""))

    assert caught.value.trace.prompt_version == QUESTIONS_VERSION
    assert [call.tool for call in caught.value.trace.tool_calls] == ["judge.decide", "llm.generate"]


@pytest.mark.parametrize(
    ("error", "status"),
    [(AIRetryableError("임베딩 호출 실패"), "FAILED"), (AITimeoutError("검색 시간 초과"), "TIMEOUT")],
)
def test_검색_오류는_NOT_FOUND로_바꾸지_않고_실패한_도구를_남긴다(error, status):
    class FailingLookup(FakeLookup):
        async def search(self, request):
            raise error

    with pytest.raises(AIRetryableError) as caught:
        _run(_request(), _judge(True, "2025 봄 MT 숙소비"), FailingLookup())

    call = caught.value.trace.tool_calls[-1]
    assert (call.tool, call.input, call.status, call.result_count) == (
        "records.search",
        "2025 봄 MT 숙소비",
        status,
        None,
    )


def test_답_작성_오류는_성공한_검색과_실패한_답_작성을_남긴다():
    class FailingLookup(FakeLookup):
        async def answer(self, request, chunks):
            raise AIRetryableError("답 작성 실패")

    with pytest.raises(AIRetryableError) as caught:
        _run(_request(), _judge(True, "2025 봄 MT 숙소비"), FailingLookup((CHUNK,)))

    assert [(call.tool, call.status) for call in caught.value.trace.tool_calls] == [
        ("judge.decide", "OK"),
        ("llm.generate", "OK"),
        ("records.search", "OK"),
        ("llm.generate", "FAILED"),
    ]


def test_검색되지_않은_출처_오류도_두_도구를_남긴다():
    lookup = FakeLookup((CHUNK,), MeetingAnswer(answer="20,000원", sources=(OTHER,)))

    with pytest.raises(AIInvalidResponseError) as caught:
        _run(_request(), _judge(True, "2025 봄 MT 숙소비"), lookup)

    assert [call.status for call in caught.value.trace.tool_calls] == ["OK", "OK", "OK", "OK"]


def test_진행_알림을_넘기지_않아도_판단한다():
    result = _run(_request(), _judge(False), progress=None)

    assert result.kind == "NO_LOOKUP"
