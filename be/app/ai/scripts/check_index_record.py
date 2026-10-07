"""기록 색인(index_record)을 실제 ML API로 확인한다 (#71).

키가 필요해 CI에서 돌리지 않는다. 청킹·임베딩 규칙이나 모델을 바꿨을 때 수동으로 실행하고
결과는 docs/retrieval-evaluation.md 에 남긴다.

    cd be && uv run python app/ai/scripts/check_index_record.py [--json 결과.json] [--no-header]

① 예시 기록 4종과 실제 PDF(BE 파서 경유)를 색인해 청크 수·길이·시간을 본다.
② 예시 기록 색인 결과를 메모리 port에 넣고 질문으로 검색해 상위 청크를 본다.
   검색 평가는 #72에서 한다. 여기서는 색인 결과가 검색에 쓸 만한지 관찰한다.
--no-header: 청크 임베딩에서 문서명·위치 이름표를 빼고 돌려 이름표의 효과를 비교한다.

AI_* 는 be/.env 에서 읽는다. 출력은 scrub()을 거쳐 키가 남지 않는다.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from statistics import mean

import httpx
from dotenv import load_dotenv

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import AISettings  # noqa: E402
from app.ai.contracts import IndexRecordRequest  # noqa: E402
from app.ai.features.retrieval.chunking import (  # noqa: E402
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
)
from app.ai.features.retrieval.indexing import index_record_chunks  # noqa: E402
from app.ai.features.retrieval.memory_port import (  # noqa: E402
    InMemoryRecordSearch,
    StoredRecord,
)
from app.ai.llm import (  # noqa: E402
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    aembed_texts,
    build_embeddings,
)
from app.ai.ports import ChunkSearchQuery  # noqa: E402
from app.core.enums import RecordCategory, RecordFileType  # noqa: E402

# 확인 스크립트라서 BE 파서로 실제 PDF를 읽는다. AI 모듈 코드는 BE 서비스를 참조하지 않는다.
from app.services.record_parser import parse_record  # noqa: E402

AI_DIR = Path(__file__).resolve().parents[1]
FIXTURES = AI_DIR / "tests" / "fixtures" / "records"
NAMES = ("rules_2024", "mt_2025_spring_report", "ledger_2025_h1", "ledger_2024_h2")
SAMPLE_PDF = AI_DIR.parents[1] / "tests" / "fixtures" / "records" / "sample_report.pdf"
SEARCH_LIMIT = 3

# (질문, 기대하는 "파일명 · 라벨"). 기대값이 None이면 관찰만 한다
QUESTIONS: tuple[tuple[str, str | None], ...] = (
    ("작년 봄 MT 때 예산을 얼마나 초과했어?", "2025 봄 MT 결과보고.pdf · 2쪽 · 3. 정산"),
    ("행사 취소하면 환불 받을 수 있어?", "동아리 회칙 (2024 개정).pdf · 2쪽 · 제10조(참가비 환불)"),
    ("30만 원 넘게 쓰려면 누구 승인이 필요해?", "동아리 회칙 (2024 개정).pdf · 3쪽 · 제12조(지출 승인)"),
    ("봄 MT는 어디로 갔고 몇 명이 참가했어?", "2025 봄 MT 결과보고.pdf · 1쪽 · 1. 행사 개요"),
    ("학기 회비는 얼마야?", "동아리 회칙 (2024 개정).pdf · 2쪽 · 제8조(학기 회비)"),
    # 2025 봄(가평)·2024 가을(양평) 숙소가 모두 있다. 어느 쪽이 먼저 잡히는지 본다 (#72 함정)
    ("MT 숙소 비용은 얼마였어?", None),
)

SECRETS: list[str] = []


def scrub(value: object) -> str:
    text = str(value)
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "***")
    return text


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


def _sample_request() -> IndexRecordRequest:
    parsed = parse_record(SAMPLE_PDF.read_bytes(), RecordFileType.PDF)
    return IndexRecordRequest(
        record_id="sample_report",
        file_name=SAMPLE_PDF.name,
        file_type=RecordFileType.PDF,
        blocks=parsed["blocks"],
    )


async def run(settings: AISettings, *, header: bool = True) -> dict:
    requests = 0

    async def count(request: httpx.Request) -> None:
        nonlocal requests
        requests += 1

    model = build_embeddings(
        settings, http_async_client=httpx.AsyncClient(event_hooks={"request": [count]})
    )

    async def embed(texts):
        return await aembed_texts(texts, model=model)

    async def embed_without_header(texts):
        # embedding_input은 "문서: …\n위치: …\n\n본문"이다. 비교 실행에서만 본문만 남긴다
        return await embed([text.split("\n\n", 1)[1] for text in texts])

    embed_chunks = embed if header else embed_without_header

    result: dict = {
        "settings": {
            "embedding_model": settings.embedding_model,
            "dimensions": EMBEDDING_DIMENSIONS,
            "chunk_max_chars": CHUNK_MAX_CHARS,
            "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
            "embedding_batch_size": EMBEDDING_BATCH_SIZE,
            "embedding_header": header,
        },
        "records": [],
        "questions": [],
    }

    # ① 색인
    print("== 색인")
    port = InMemoryRecordSearch()
    targets = [(*_load(name), True) for name in NAMES] + [(_sample_request(), None, False)]
    for request, stored, searchable in targets:
        before, started = requests, time.perf_counter()
        indexed = await index_record_chunks(request, embed=embed_chunks)
        seconds = time.perf_counter() - started
        lengths = [len(chunk.text) for chunk in indexed.chunks]
        row = {
            "file_name": request.file_name,
            "blocks": len(request.blocks),
            "chunks": len(indexed.chunks),
            "chars_min": min(lengths),
            "chars_avg": round(mean(lengths)),
            "chars_max": max(lengths),
            "requests": requests - before,
            "seconds": round(seconds, 2),
            "dimensions_ok": all(len(c.embedding) == EMBEDDING_DIMENSIONS for c in indexed.chunks),
            "labels": [chunk.location.label for chunk in indexed.chunks],
        }
        result["records"].append(row)
        print(
            f"- {row['file_name']}: 블록 {row['blocks']} → 청크 {row['chunks']} "
            f"(글자 {row['chars_min']}/{row['chars_avg']}/{row['chars_max']}), "
            f"요청 {row['requests']}회, {row['seconds']}초, 차원 {'OK' if row['dimensions_ok'] else 'FAIL'}"
        )
        for label in row["labels"]:
            print(f"    {label}")
        if searchable:
            port.add(stored, indexed.chunks)

    # ② 검색 관찰
    print("\n== 검색 (예시 기록 4종, 상위 3개)")
    vectors = await embed([question for question, _ in QUESTIONS])
    for (question, expected), vector in zip(QUESTIONS, vectors, strict=True):
        found = await port.search_chunks(
            ChunkSearchQuery(club_id="clb_keunnamu", embedding=vector, limit=SEARCH_LIMIT)
        )
        top = [
            {
                "source": f"{chunk.source.file_name} · {chunk.source.location.label}",
                "score": round(chunk.score, 4),
            }
            for chunk in found
        ]
        rank = next((i + 1 for i, t in enumerate(top) if t["source"] == expected), None)
        result["questions"].append(
            {"question": question, "expected": expected, "rank": rank, "top": top}
        )
        mark = "관찰" if expected is None else (f"{rank}위" if rank else "상위 3개 밖")
        print(f"- [{mark}] {question}")
        for i, t in enumerate(top, start=1):
            print(f"    {i}. {t['score']:.4f}  {t['source']}")

    judged = [q for q in result["questions"] if q["expected"] is not None]
    result["summary"] = {
        "questions": len(judged),
        "hit_at_1": sum(q["rank"] == 1 for q in judged),
        "hit_at_3": sum(q["rank"] is not None for q in judged),
        "requests": requests,
    }
    s = result["summary"]
    print(f"\n== 요약: 기대 질문 {s['questions']}개 중 1위 {s['hit_at_1']}, 3위 안 {s['hit_at_3']}, "
          f"임베딩 요청 {s['requests']}회")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="결과를 JSON으로 저장할 경로")
    parser.add_argument("--no-header", action="store_true", help="이름표 없이 임베딩해 비교한다")
    args = parser.parse_args()

    settings = AISettings()
    SECRETS.extend(
        [settings.api_key.get_secret_value(), settings.resolved_embedding_api_key.get_secret_value()]
    )
    settings.require_embedding()
    print(scrub(f"model={settings.embedding_model} header={not args.no_header}"))

    try:
        result = asyncio.run(run(settings, header=not args.no_header))
    except Exception as error:  # noqa: BLE001 - 확인 스크립트는 원인만 보여주고 끝낸다
        print(scrub(f"[FAIL] {type(error).__name__}: {error}"))
        return 1

    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"결과 저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
