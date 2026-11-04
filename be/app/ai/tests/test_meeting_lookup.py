"""판단 → 기록 검색 → 근거 판단이 이어져 회의 결과 하나가 되는지 검증한다.

판단·임베딩·근거 판단 모델은 가짜로, 기록은 메모리 검색 port로 둔다.
가짜끼리 잇지 않고 실제 find_chunks·assess_chunks와 카드 변환을 거친다.
"""

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from app.ai.config import get_settings
from app.ai.contracts import IndexedChunk, RecordSource, SourceLocation
from app.ai.errors import AIError, AIInvalidResponseError, AITimeoutError
from app.ai.features.meeting.lookup import MEETING_ASSESS_PROMPT_VERSION, RecordsLookup, get_assess_model, to_meeting_answer
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.schemas import (
    QueryOutput,
    JudgeUtteranceRequest,
    MeetingSearchRequest,
    MeetingUtterance,
)
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.features.retrieval.schemas import (
    EvidenceAssessment,
    EvidenceItem,
    RecordConflict,
    RecordFact,
    RecordSearchResult,
    RecordSearchRequest,
)
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.core.enums import RecordCategory

CLUB = "clb_keunnamu"
AT = datetime(2026, 3, 5, 5, 0, tzinfo=timezone.utc)
QUESTION = "2025 봄 MT 숙소비"

REPORT = RecordSource(
    record_id="rec_mt", file_name="2025 봄 MT 결과보고.pdf", location=SourceLocation(label="2쪽 · 2. 예산")
)
LEDGER = RecordSource(
    record_id="rec_ledger", file_name="2025 상반기 장부.xlsx", location=SourceLocation(label="지출 시트")
)

# 칸 하나가 낱말 하나다
KEYWORDS = ("숙소", "회비")


def _vector(text: str) -> tuple[float, ...]:
    counts = tuple(float(text.count(word)) for word in KEYWORDS)
    return counts + (0.0,) * (EMBEDDING_DIMENSIONS - len(counts))


async def _embed(texts: Sequence[str]) -> list[tuple[float, ...]]:
    return [_vector(text) for text in texts]


@pytest.fixture(autouse=True)
def _model_name(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "gpt-5.6-luna")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- 카드 변환 ------------------------------------------------------------------


def test_사실은_한_줄에_하나씩_그대로_옮긴다():
    result = RecordSearchResult(
        facts=(
            RecordFact(content="2025 봄 MT 숙박비 550,000원", sources=(REPORT,)),
            RecordFact(content="2025 봄 MT 펜션 잔금 550,000원", sources=(LEDGER, REPORT)),
        )
    )

    answer = to_meeting_answer(result)

    assert answer.answer == "2025 봄 MT 숙박비 550,000원\n2025 봄 MT 펜션 잔금 550,000원"
    # 같은 출처는 한 번만, 나온 순서대로
    assert answer.sources == (REPORT, LEDGER)


def test_자료_간_차이는_하나를_고르지_않고_값마다_문서_이름을_붙인다():
    result = RecordSearchResult(
        conflicts=(
            RecordConflict(
                description="2025 봄 MT 참가 인원",
                values=(
                    RecordFact(content="28명", sources=(REPORT,)),
                    RecordFact(content="27명", sources=(LEDGER,)),
                ),
            ),
        )
    )

    answer = to_meeting_answer(result)

    assert answer.answer == (
        "2025 봄 MT 참가 인원: 28명 (2025 봄 MT 결과보고.pdf) / 27명 (2025 상반기 장부.xlsx)"
    )
    assert answer.sources == (REPORT, LEDGER)


def test_확인한_것과_확인하지_못한_것이_섞이면_뒤에_덧붙인다():
    result = RecordSearchResult(
        facts=(RecordFact(content="2025 봄 MT 숙박비 550,000원", sources=(REPORT,)),),
        not_found=("숙소비 세부 내역",),
    )

    assert to_meeting_answer(result).answer == (
        "2025 봄 MT 숙박비 550,000원\n검색한 자료에서 확인하지 못함: 숙소비 세부 내역"
    )


def test_확인하지_못한_것뿐이면_기록에_없음이다():
    assert to_meeting_answer(RecordSearchResult(not_found=(QUESTION,))) is None


# --- 판단부터 이어서 ----------------------------------------------------------------


def _port() -> InMemoryRecordSearch:
    """숙소비가 적힌 결과보고 하나와 회비가 적힌 회칙 하나"""
    port = InMemoryRecordSearch()
    for record_id, file_name, label, text in (
        ("rec_mt", "2025 봄 MT 결과보고.pdf", "2쪽 · 2. 예산", "숙소 펜션 550,000원"),
        ("rec_rules", "동아리 회칙.pdf", "2쪽 · 제8조(학기 회비)", "학기 회비 20,000원"),
    ):
        port.add(
            StoredRecord(
                record_id=record_id, club_id=CLUB, file_name=file_name, category=RecordCategory.ETC
            ),
            [
                IndexedChunk(
                    text=text,
                    location=SourceLocation(label=label),
                    block_indexes=(0,),
                    embedding=_vector(f"{file_name} {text}"),
                )
            ],
        )
    return port


class FakeInvoke:
    """정해 둔 근거 판단을 돌려주고 받은 메시지를 남긴다"""

    def __init__(self, assessment: EvidenceAssessment | None = None) -> None:
        self.assessment = assessment
        self.calls: list = []

    async def __call__(self, messages, schema):
        self.calls.append(messages)
        assert schema is EvidenceAssessment
        return self.assessment


def _assessment(**overrides) -> EvidenceAssessment:
    values = {"sufficient": True, "retry_queries": [], "facts": [], "not_found": [], "conflicts": []}
    return EvidenceAssessment(**(values | overrides))


async def _decide(state):
    """Jev 대신 조회로 본다"""
    return 0.9


async def _query(messages):
    """luna 대신 검색어를 돌려준다"""
    return QueryOutput(query=QUESTION)


def _run(port, invoke, embed=_embed):
    request = JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id=CLUB,
        utterance=MeetingUtterance(
            utterance_id="u-31", seq=31, text="작년 MT 숙소비 얼마였지?", started_at=AT, ended_at=AT
        ),
    )
    lookup = RecordsLookup(port, embed=embed, invoke=invoke)
    return asyncio.run(judge_utterance(request, lookup=lookup, decide=_decide, query=_query))


def test_찾은_청크의_근거로_답하고_출처는_검색된_기록이다():
    # 숙소 조각이 먼저 찾아져 c1이 된다
    invoke = FakeInvoke(
        _assessment(facts=[EvidenceItem(content="2025 봄 MT 숙박비 550,000원", chunk_ids=["c1"])])
    )

    result = _run(_port(), invoke)

    assert (result.kind, result.question) == ("ANSWER", QUESTION)
    assert result.answer == "2025 봄 MT 숙박비 550,000원"
    assert [source.record_id for source in result.sources] == ["rec_mt"]
    # 앞의 두 줄은 판단(Jev)과 검색어(luna)다
    search, answer = result.trace.tool_calls[2:]
    assert (search.tool, search.status, search.result_count) == ("records.search", "OK", 2)
    assert (answer.tool, answer.status) == ("llm.generate", "OK")
    # 어떤 근거 판단 지시문으로 답했는지 판단 기록에 남는다
    assert (search.prompt_version, answer.prompt_version) == (None, MEETING_ASSESS_PROMPT_VERSION)


def test_근거_판단은_다시_찾지_않고_회의_날짜를_기준일로_본다():
    invoke = FakeInvoke(_assessment(not_found=[QUESTION]))

    _run(_port(), invoke)

    [messages] = invoke.calls
    prompt = messages[1].content
    assert "오늘: 2026-03-05" in prompt
    assert f"찾을 내용: {QUESTION}" in prompt
    assert "다시 찾을 수 있는 횟수: 0" in prompt
    assert "작년 MT 숙소비 얼마였지?" in messages[-1].content


def test_올린_기록이_없으면_근거_판단을_부르지_않고_기록에_없음이다():
    invoke = FakeInvoke()

    result = _run(InMemoryRecordSearch(), invoke)

    assert result.kind == "NOT_FOUND"
    assert invoke.calls == []
    assert [call.tool for call in result.trace.tool_calls[2:]] == ["records.search"]


def test_청크는_찾았지만_근거가_없으면_기록에_없음이다():
    result = _run(_port(), FakeInvoke(_assessment(not_found=[QUESTION])))

    assert (result.kind, result.answer, result.sources) == ("NOT_FOUND", None, ())
    assert [call.status for call in result.trace.tool_calls[2:]] == ["OK", "OK"]


def test_받지_않은_자료를_가리키면_근거_판단에서_실패했다고_남긴다():
    invoke = FakeInvoke(
        _assessment(facts=[EvidenceItem(content="550,000원", chunk_ids=["c9"])])
    )

    with pytest.raises(AIInvalidResponseError) as raised:
        _run(_port(), invoke)

    search, answer = raised.value.trace.tool_calls[2:]
    assert (search.tool, search.status) == ("records.search", "OK")
    assert (answer.tool, answer.status) == ("llm.generate", "FAILED")
    assert answer.prompt_version == MEETING_ASSESS_PROMPT_VERSION


def test_임베딩이_늦으면_검색에서_멈추고_시간_초과로_남긴다():
    async def slow_embed(texts):
        raise AITimeoutError("모델 응답이 제한 시간 안에 오지 않았습니다")

    with pytest.raises(AIError) as raised:
        _run(_port(), FakeInvoke(), embed=slow_embed)

    [search] = raised.value.trace.tool_calls[2:]
    assert (search.tool, search.status) == ("records.search", "TIMEOUT")


def test_회의의_근거_판단은_추론을_끈_모델로_부른다(monkeypatch):
    monkeypatch.setenv("AI_API_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    get_settings.cache_clear()
    get_assess_model.cache_clear()

    assert get_assess_model().reasoning == {"effort": "none"}
    get_assess_model.cache_clear()


@pytest.mark.parametrize(('query', 'relevant'), [
    ('2026 봄 MT 회고 내용', '둘째 날 행사 회고를 진행했다.'),
    ('가장 최근 행사 참가 인원', '실제 참가 인원은 48명이다.'),
])
def test_회의_회고와_최근_인원은_넓은_후보에서_관련_본문을_고른다(monkeypatch, query, relevant):
    from app.ai.features.meeting import lookup as meeting_lookup
    from app.ai.ports import RetrievedChunk
    seen = []
    async def find(request, *, port, embed):
        seen.append(request.limit)
        source = RecordSource(record_id='r', file_name='2026 행사.pdf', location=SourceLocation(label='1쪽'))
        return tuple(RetrievedChunk(text=text, source=source, category=RecordCategory.ETC, score=score)
                     for text, score in [('제목', .8), ('행사 개요', .79), ('예산', .78),
                                         ('일정', .77), ('홍보', .76), (relevant, .65)])
    monkeypatch.setattr(meeting_lookup, 'find_chunks', find)
    request = RecordSearchRequest(club_id=CLUB, query=query, today='2026-11-03')
    result = asyncio.run(RecordsLookup(_port()).search(request))
    assert seen == [20] and len(result) == 5 and any(chunk.text == relevant for chunk in result)


def test_일반_검색은_기존_후보_개수를_유지한다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    seen = []
    async def find(request, *, port, embed):
        seen.append(request.limit)
        return ()
    monkeypatch.setattr(meeting_lookup, 'find_chunks', find)
    request = RecordSearchRequest(club_id=CLUB, query='2025 가을 MT 버스비', today='2026-11-03')
    assert asyncio.run(RecordsLookup(_port()).search(request)) == ()
    assert seen == [5]


def test_최근_답변은_전체_최신성을_단정하지_않는다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    async def assess(request, chunks, *, invoke, filter_assessment):
        return RecordSearchResult(facts=(RecordFact(content='2026 가을 교류회 실제 참가자 48명', sources=(REPORT,)),))
    monkeypatch.setattr(meeting_lookup, 'assess_chunks', assess)
    request = RecordSearchRequest(club_id=CLUB, query='가장 최근 행사 참가 인원', today='2026-11-03')
    answer = asyncio.run(RecordsLookup(_port()).answer(request, ()))
    assert '검색된 자료 기준' in answer.answer and '전체 자료에서 가장 최근인지 확인하지 못했어요' in answer.answer
    assert answer.sources == (REPORT,)


def test_검색어에서_최근이_빠져도_원발화로_최신_한계를_표시한다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    async def assess(request, chunks, *, invoke, filter_assessment):
        return RecordSearchResult(facts=(RecordFact(content='2026 가을 교류회 실제 참가자 48명', sources=(REPORT,)),))
    monkeypatch.setattr(meeting_lookup, 'assess_chunks', assess)
    request = MeetingSearchRequest(
        club_id=CLUB, query='행사 참가 인원', today='2026-11-03',
        original_question='가장 최근 행사 참가 인원은?',
    )
    answer = asyncio.run(RecordsLookup(_port()).answer(request, ()))
    assert '전체 자료에서 가장 최근인지 확인하지 못했어요' in answer.answer


def test_검색어에서_최근이_빠져도_원발화로_참가_본문을_보충한다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    from app.ai.ports import RetrievedChunk
    seen = []
    async def find(request, *, port, embed):
        seen.append(request.limit)
        return tuple(RetrievedChunk(text=text, source=REPORT, category=RecordCategory.ETC, score=.5)
                     for text in ('제목', '개요', '예산', '일정', '홍보', '실제 참가 인원 48명'))
    monkeypatch.setattr(meeting_lookup, 'find_chunks', find)
    request = MeetingSearchRequest(club_id=CLUB, query='행사 참가 인원', today='2026-11-03',
                                   original_question='가장 최근 행사 참가 인원은?')
    result = asyncio.run(RecordsLookup(_port()).search(request))
    assert seen == [20]
    assert any(chunk.text == '실제 참가 인원 48명' for chunk in result)


def test_회고_검색은_다른_연도에_원래_상위_결과를_잃지_않는다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    from app.ai.ports import RetrievedChunk
    def make(year, text, score):
        return RetrievedChunk(text=text, source=RecordSource(record_id=f'r{year}',
            file_name=f'{year} 가을MT.pdf', location=SourceLocation(label='1쪽')),
            category=RecordCategory.EVENT_HISTORY, score=score)
    candidates = tuple(make('2026', f'2026 가을 MT 후속 평가 {i}', .80 - i * .01) for i in range(5)) + tuple(
        make('2023', f'2023 여름 MT 회고 {i}', .70 - i * .01) for i in range(5))
    async def find(request, *, port, embed): return candidates
    monkeypatch.setattr(meeting_lookup, 'find_chunks', find)
    request = RecordSearchRequest(club_id=CLUB, query='2026 가을 MT 회고', today='2026-11-03')
    result = asyncio.run(RecordsLookup(_port()).search(request))
    assert all('2026' in chunk.source.file_name for chunk in result)


def test_최근_인원과_회고를_함께_물으면_두_항목을_유지한다(monkeypatch):
    from app.ai.features.meeting import lookup as meeting_lookup
    from app.ai.ports import RetrievedChunk
    def make(text, i, score):
        return RetrievedChunk(text=text, source=RecordSource(record_id=f'r{i}',
            file_name=f'행사{i}.pdf', location=SourceLocation(label='1쪽')),
            category=RecordCategory.EVENT_HISTORY, score=score)
    candidates = tuple(make(f'실제 참가 인원 {i}명', i, .80 - i * .01) for i in range(5)) + tuple(
        make(f'행사 회고 {i}', i + 5, .70 - i * .01) for i in range(5))
    async def find(request, *, port, embed): return candidates
    monkeypatch.setattr(meeting_lookup, 'find_chunks', find)
    request = RecordSearchRequest(club_id=CLUB, query='최근 행사 참가 인원과 회고', today='2026-11-03')
    result = asyncio.run(RecordsLookup(_port()).search(request))
    assert any('참가 인원' in chunk.text for chunk in result)
    assert any('회고' in chunk.text for chunk in result)


def test_근거에_없는_금액은_제거하고_확인된_금액과_출처는_보존한다():
    invoke = FakeInvoke(_assessment(facts=[
        EvidenceItem(content='2025 봄 MT 숙박비 550,000원', chunk_ids=['c1']),
        EvidenceItem(content='2025 봄 MT 교통비 999,000원', chunk_ids=['c1']),
    ]))
    result = _run(_port(), invoke)
    assert result.kind == 'ANSWER'
    assert '550,000원' in result.answer and '999,000원' not in result.answer
    assert '확인하지 못함' in result.answer
    assert result.sources[0].record_id == 'rec_mt'


def test_출처에_없는_연도를_추정한_답은_미확인이다():
    port = InMemoryRecordSearch()
    port.add(StoredRecord(record_id='r', club_id=CLUB, file_name='MT 보고.pdf', category=RecordCategory.ETC),
             [IndexedChunk(text='숙소 펜션 550,000원', location=SourceLocation(label='1쪽'),
                           block_indexes=(0,), embedding=_vector('숙소'))])
    invoke = FakeInvoke(_assessment(facts=[EvidenceItem(content='2025 봄 MT 숙박비 550,000원', chunk_ids=['c1'])]))
    assert _run(port, invoke).kind == 'NOT_FOUND'
