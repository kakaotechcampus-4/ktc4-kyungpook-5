"""기록 검색 평가 질문이 형식에 맞고, 정답 출처가 예시 기록의 실제 청크를 가리키는지 검증한다.

청킹 규칙이 바뀌어 라벨이 달라지면 여기서 드러난다.
"""

import asyncio
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from app.ai.contracts import EventConditions, IndexRecordRequest
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.llm import EMBEDDING_DIMENSIONS

FIXTURES = Path(__file__).parent / "fixtures"
QUESTIONS = json.loads(
    (FIXTURES / "eval" / "questions.json").read_text(encoding="utf-8")
)
REQUIREMENTS = {"AI-PLAN-04", "AI-RET-01", "AI-RET-03", "AI-COMMON-01"}
# 원문 확인을 건너뛰는 (질문, 기록). q42의 장부 납부 인원 27은 회비 수납 행을 세야 나오는
# 값이라 원문에 그대로 없다. 결과보고 정산(28명)과의 충돌을 재려고 장부를 출처로 둔다
COUNTED_SOURCES = {("q42", "rec_ledger_2025_h1")}


async def _zero_embed(texts: Sequence[str]) -> list[tuple[float, ...]]:
    return [(0.0,) * EMBEDDING_DIMENSIONS for _ in texts]


def _record_chunks() -> dict[str, tuple[str, dict[str, list[str]]]]:
    """기록 id → (파일명, 라벨 → 청크 원문 목록)"""
    records = {}
    for path in sorted((FIXTURES / "records").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data["record"]
        request = IndexRecordRequest(
            record_id=record["id"],
            file_name=record["file_name"],
            file_type=record["file_type"],
            blocks=data["parse_result"]["blocks"],
        )
        result = asyncio.run(index_record_chunks(request, embed=_zero_embed))
        texts: dict[str, list[str]] = {}
        for chunk in result.chunks:
            texts.setdefault(chunk.location.label, []).append(chunk.text)
        records[record["id"]] = (record["file_name"], texts)
    return records


RECORDS = _record_chunks()


def _items(expected: dict) -> list[dict]:
    """정답 사실과 충돌 값. 모두 content와 sources를 가진다"""
    return expected["facts"] + [
        value for conflict in expected["conflicts"] for value in conflict["values"]
    ]


def test_질문은_50개이고_확인용은_12개다():
    assert len(QUESTIONS) == 50
    assert len({question["id"] for question in QUESTIONS}) == 50
    assert sum(question["split"] == "holdout" for question in QUESTIONS) == 12


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda question: question["id"])
def test_질문은_정해진_형식이다(question):
    assert set(question) - {"note"} == {
        "id",
        "split",
        "requirement",
        "question",
        "today",
        "conditions",
        "expected",
    }
    assert question["split"] in {"dev", "holdout"}
    assert question["requirement"] in REQUIREMENTS
    assert question["question"].strip()
    date.fromisoformat(question["today"])
    if question["conditions"] is not None:
        EventConditions(**question["conditions"])

    # "없음"은 빈 목록으로만 적는다. 필드가 빠지면 라벨 누락이다
    expected = question["expected"]
    assert set(expected) == {"facts", "not_found", "conflicts"}
    assert expected["facts"] or expected["not_found"] or expected["conflicts"]
    assert all(text.strip() for text in expected["not_found"])
    for conflict in expected["conflicts"]:
        assert set(conflict) == {"description", "values"}
        assert conflict["description"].strip()
        assert len(conflict["values"]) >= 2


@pytest.mark.parametrize("question", QUESTIONS, ids=lambda question: question["id"])
def test_정답_값은_모든_출처_청크의_원문에_있다(question):
    for item in _items(question["expected"]):
        assert set(item) == {"content", "sources"}
        assert item["content"].strip()
        assert item["sources"]

        for source in item["sources"]:
            assert source["record_id"] in RECORDS, source
            file_name, texts = RECORDS[source["record_id"]]
            assert source["file_name"] == file_name, source
            label = source["location"]["label"]
            assert label in texts, f"{source['record_id']}에 '{label}' 청크가 없다"
            if (question["id"], source["record_id"]) in COUNTED_SOURCES:
                continue
            assert any(item["content"] in text for text in texts[label]), (
                f"'{item['content']}'이 {source['record_id']} '{label}' 원문에 없다"
            )
