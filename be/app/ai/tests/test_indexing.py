"""기록 색인이 청킹·임베딩을 이어 계약에 맞는 결과를 내는지 검증한다.

ML API 대신 낱말이 들어 있는 칸에 개수를 넣는 가짜 임베딩을 쓴다.
같은 낱말을 가진 글끼리 가까워져 검색 결과를 확인할 수 있다.
"""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.ai.contracts import IndexRecordRequest
from app.ai.errors import AIRetryableError
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.ai.ports import ChunkSearchQuery
from app.core.enums import RecordCategory

FIXTURES = Path(__file__).parent / "fixtures" / "records"
NAMES = ("rules_2024", "mt_2025_spring_report", "ledger_2025_h1", "ledger_2024_h2")
CLUB = "clb_keunnamu"

# 칸 하나가 낱말 하나다
KEYWORDS = ("환불", "회비", "예비비", "장소", "숙소", "정산")


def _keyword_vector(text: str) -> tuple[float, ...]:
    counts = tuple(float(text.count(word)) for word in KEYWORDS)
    return counts + (0.0,) * (EMBEDDING_DIMENSIONS - len(counts))


async def _fake_embed(texts: Sequence[str]) -> list[tuple[float, ...]]:
    return [_keyword_vector(text) for text in texts]


def _load(name: str) -> tuple[IndexRecordRequest, StoredRecord]:
    data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    record = data["record"]
    request = IndexRecordRequest(
        record_id=record["id"],
        file_name=record["file_name"],
        file_type=record["file_type"],
        blocks=data["parse_result"]["blocks"],
    )
    stored = StoredRecord(
        record_id=record["id"],
        club_id=record["club_id"],
        file_name=record["file_name"],
        category=RecordCategory(record["category"]),
        event_id=record["event_id"],
    )
    return request, stored


def _index(request: IndexRecordRequest, embed=_fake_embed):
    return asyncio.run(index_record_chunks(request, embed=embed))


@pytest.mark.parametrize(
    ("name", "count"),
    [("rules_2024", 7), ("mt_2025_spring_report", 4), ("ledger_2025_h1", 3), ("ledger_2024_h2", 1)],
)
def test_예시_기록을_형식에_맞게_청크로_나눈다(name, count):
    request, _ = _load(name)

    result = _index(request)

    assert len(result.chunks) == count


def test_임베딩에는_이름표를_붙인_글을_보내고_결과_text는_원문이다():
    request, _ = _load("mt_2025_spring_report")
    sent: list[str] = []

    async def embed(texts):
        sent.extend(texts)
        return await _fake_embed(texts)

    result = _index(request, embed)

    assert sent[2].startswith("문서: 2025 봄 MT 결과보고.pdf\n위치: 2쪽 · 3. 정산\n\n3. 정산")
    assert result.chunks[2].text.startswith("3. 정산")


@pytest.mark.parametrize("name", NAMES)
def test_청크의_블록_번호로_원본_블록을_찾을_수_있다(name):
    request, _ = _load(name)

    result = _index(request)

    for chunk in result.chunks:
        source_lines = {
            line for index in chunk.block_indexes for line in request.blocks[index].text.splitlines()
        }
        assert set(chunk.text.splitlines()) <= source_lines


def test_파일_없는_텍스트_기록은_문서로_나눈다():
    request = IndexRecordRequest(
        record_id="rec_feedback",
        file_name="2025 봄 MT 회고",
        file_type=None,
        blocks=({"text": "1. 좋았던 점\n바비큐장이 넓었다.", "location": {"label": "운영진 회고"}},),
    )

    result = _index(request)

    assert [chunk.location.label for chunk in result.chunks] == ["운영진 회고 · 1. 좋았던 점"]


def test_임베딩_오류는_빈_결과_대신_그대로_올라간다():
    request, _ = _load("rules_2024")

    async def failing(texts):
        raise AIRetryableError("모델 API에 연결하지 못했습니다")

    with pytest.raises(AIRetryableError):
        _index(request, failing)


# --- 색인 → 저장(메모리 port) → 검색 ------------------------------------------


@pytest.fixture
def search() -> InMemoryRecordSearch:
    """예시 기록 4종을 색인해 BE 대신 메모리 port에 저장한다"""
    port = InMemoryRecordSearch()
    for name in NAMES:
        request, stored = _load(name)
        port.add(stored, _index(request).chunks)
    return port


def _search(port, question: str, **filters):
    query = ChunkSearchQuery(club_id=CLUB, embedding=_keyword_vector(question), limit=3, **filters)
    return asyncio.run(port.search_chunks(query))


def test_색인한_청크를_검색하면_해당_조항과_출처가_나온다(search):
    top = _search(search, "환불")[0]

    assert top.source.record_id == "rec_rules_2024"
    assert top.source.file_name == "동아리 회칙 (2024 개정).pdf"
    assert top.source.location.label == "2쪽 · 제10조(참가비 환불)"
    assert "3. 그 이후: 환불하지 않는다." in top.text


def test_분류_필터를_주면_그_분류의_청크에서만_찾는다(search):
    found = _search(search, "예비비", category=RecordCategory.LEDGER)

    assert found[0].source.location.label == "지출 시트 · 2~9행"
    assert all(chunk.category == RecordCategory.LEDGER for chunk in found)
