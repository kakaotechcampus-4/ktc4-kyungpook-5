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
from app.ai.features.meeting.lookup import RecordsLookup, to_meeting_answer
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.schemas import (
    JudgeOutput,
    JudgeUtteranceRequest,
    MeetingUtterance,
)
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.features.retrieval.schemas import (
    EvidenceAssessment,
    EvidenceItem,
    RecordConflict,
    RecordFact,
    RecordSearchResult,
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
        "2025 봄 MT 숙박비 550,000원\n기록에 없음: 숙소비 세부 내역"
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


async def _judge(messages):
    return JudgeOutput(needs_lookup=True, query=QUESTION)


def _run(port, invoke, embed=_embed):
    request = JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id=CLUB,
        utterance=MeetingUtterance(
            utterance_id="u-31", seq=31, text="작년 MT 숙소비 얼마였지?", started_at=AT, ended_at=AT
        ),
    )
    lookup = RecordsLookup(port, embed=embed, invoke=invoke)
    return asyncio.run(judge_utterance(request, lookup=lookup, judge=_judge))


def test_찾은_청크의_근거로_답하고_출처는_검색된_기록이다():
    # 숙소 조각이 먼저 찾아져 c1이 된다
    invoke = FakeInvoke(
        _assessment(facts=[EvidenceItem(content="2025 봄 MT 숙박비 550,000원", chunk_ids=["c1"])])
    )

    result = _run(_port(), invoke)

    assert (result.kind, result.question) == ("ANSWER", QUESTION)
    assert result.answer == "2025 봄 MT 숙박비 550,000원"
    assert [source.record_id for source in result.sources] == ["rec_mt"]
    search, answer = result.trace.tool_calls
    assert (search.tool, search.status, search.result_count) == ("records.search", "OK", 2)
    assert (answer.tool, answer.status) == ("llm.generate", "OK")


def test_근거_판단은_다시_찾지_않고_회의_날짜를_기준일로_본다():
    invoke = FakeInvoke(_assessment(not_found=[QUESTION]))

    _run(_port(), invoke)

    [messages] = invoke.calls
    prompt = messages[1].content
    assert "오늘: 2026-03-05" in prompt
    assert f"찾을 내용: {QUESTION}" in prompt
    assert "다시 찾을 수 있는 횟수: 0" in prompt


def test_올린_기록이_없으면_근거_판단을_부르지_않고_기록에_없음이다():
    invoke = FakeInvoke()

    result = _run(InMemoryRecordSearch(), invoke)

    assert result.kind == "NOT_FOUND"
    assert invoke.calls == []
    assert [call.tool for call in result.trace.tool_calls] == ["records.search"]


def test_청크는_찾았지만_근거가_없으면_기록에_없음이다():
    result = _run(_port(), FakeInvoke(_assessment(not_found=[QUESTION])))

    assert (result.kind, result.answer, result.sources) == ("NOT_FOUND", None, ())
    assert [call.status for call in result.trace.tool_calls] == ["OK", "OK"]


def test_받지_않은_자료를_가리키면_근거_판단에서_실패했다고_남긴다():
    invoke = FakeInvoke(
        _assessment(facts=[EvidenceItem(content="550,000원", chunk_ids=["c9"])])
    )

    with pytest.raises(AIInvalidResponseError) as raised:
        _run(_port(), invoke)

    search, answer = raised.value.trace.tool_calls
    assert (search.tool, search.status) == ("records.search", "OK")
    assert (answer.tool, answer.status) == ("llm.generate", "FAILED")


def test_임베딩이_늦으면_검색에서_멈추고_시간_초과로_남긴다():
    async def slow_embed(texts):
        raise AITimeoutError("모델 응답이 제한 시간 안에 오지 않았습니다")

    with pytest.raises(AIError) as raised:
        _run(_port(), FakeInvoke(), embed=slow_embed)

    [search] = raised.value.trace.tool_calls
    assert (search.tool, search.status) == ("records.search", "TIMEOUT")
