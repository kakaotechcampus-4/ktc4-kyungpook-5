"""메모리 기록 검색 port가 BE 구현과 같은 약속을 지키는지 검증한다."""

import asyncio

from app.ai.contracts import IndexedChunk, SourceLocation
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.llm import EMBEDDING_DIMENSIONS
from app.ai.ports import ChunkSearchQuery
from app.core.enums import RecordCategory

CLUB = "clb_keunnamu"


def _vector(*weights: float) -> tuple[float, ...]:
    """앞 칸에 가중치를 둔 1536차원 벡터. 칸 하나를 주제 하나로 본다"""
    return weights + (0.0,) * (EMBEDDING_DIMENSIONS - len(weights))


FEE = _vector(1.0)  # "회비" 방향
PLACE = _vector(0.0, 1.0)  # "장소" 방향


def _chunk(text: str, embedding: tuple[float, ...], label: str = "1쪽") -> IndexedChunk:
    return IndexedChunk(
        text=text,
        location=SourceLocation(label=label),
        block_indexes=(0,),
        embedding=embedding,
    )


def _record(record_id: str, **overrides) -> StoredRecord:
    values = {
        "record_id": record_id,
        "club_id": CLUB,
        "file_name": f"{record_id}.pdf",
        "category": RecordCategory.PLAN,
    } | overrides
    return StoredRecord(**values)


def _search(port: InMemoryRecordSearch, embedding=FEE, limit=5, **filters):
    query = ChunkSearchQuery(club_id=CLUB, embedding=embedding, limit=limit, **filters)
    return asyncio.run(port.search_chunks(query))


def test_다른_동아리_청크는_비슷해도_나오지_않는다():
    port = InMemoryRecordSearch()
    port.add(_record("rec_other", club_id="clb_other"), [_chunk("회비 45,000원", FEE)])

    assert _search(port) == ()


def test_유사도_높은_순서로_limit개까지_돌려준다():
    port = InMemoryRecordSearch()
    port.add(
        _record("rec_mt"),
        [
            _chunk("장소는 가평", PLACE),
            _chunk("회비 45,000원", FEE),
            _chunk("회비와 장소", _vector(1.0, 1.0)),
        ],
    )

    found = _search(port, limit=2)

    assert [chunk.text for chunk in found] == ["회비 45,000원", "회비와 장소"]
    assert found[0].score == 1.0


def test_분류와_행사로_거를_수_있다():
    port = InMemoryRecordSearch()
    port.add(_record("rec_rules", category=RecordCategory.NOTICE), [_chunk("회비 20,000원", FEE)])
    port.add(_record("rec_feedback", event_id="evt_mt"), [_chunk("회비 45,000원", FEE)])

    by_category = _search(port, category=RecordCategory.NOTICE)
    by_event = _search(port, event_id="evt_mt")

    assert [chunk.source.record_id for chunk in by_category] == ["rec_rules"]
    assert [chunk.source.record_id for chunk in by_event] == ["rec_feedback"]


def test_기록이_없으면_빈_결과가_정상이다():
    assert _search(InMemoryRecordSearch()) == ()


def test_같은_기록을_다시_넣으면_이전_청크가_사라진다():
    port = InMemoryRecordSearch()
    port.add(_record("rec_mt"), [_chunk("회비 40,000원", FEE)])
    port.add(_record("rec_mt"), [_chunk("회비 45,000원", FEE)])

    assert [chunk.text for chunk in _search(port)] == ["회비 45,000원"]


def test_출처에_기록_메타데이터와_청크_위치가_들어간다():
    port = InMemoryRecordSearch()
    port.add(
        _record("rec_mt", file_name="2025 봄 MT 결과보고.pdf"),
        [_chunk("회비 45,000원", FEE, label="2쪽 · 예산 항목")],
    )

    source = _search(port)[0].source

    assert source.record_id == "rec_mt"
    assert source.file_name == "2025 봄 MT 결과보고.pdf"
    assert source.location.label == "2쪽 · 예산 항목"
