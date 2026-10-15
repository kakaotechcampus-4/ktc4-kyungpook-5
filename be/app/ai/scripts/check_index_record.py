"""기록 색인(index_record)을 실제 ML API로 확인한다 (#71).

키가 필요해 CI에서 돌리지 않는다. 청킹·임베딩 규칙이나 모델을 바꿨을 때 수동으로 실행하고
결과는 docs/retrieval-evaluation.md 에 남긴다.

    cd be && uv run python app/ai/scripts/check_index_record.py [--json 결과.json]

예시 기록 4종과 실제 PDF(BE 파서 경유)를 색인해 청크 수·길이·시간을 본다.
검색 평가는 eval_retrieval.py 가 한다.

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
from app.ai.features.retrieval.memory_port import StoredRecord  # noqa: E402
from app.ai.llm import (  # noqa: E402
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    aembed_texts,
    build_embeddings,
)
from app.core.enums import RecordCategory, RecordFileType  # noqa: E402

# 확인 스크립트라서 BE 파서로 실제 PDF를 읽는다. AI 모듈 코드는 BE 서비스를 참조하지 않는다.
from app.services.record_parser import parse_record  # noqa: E402

AI_DIR = Path(__file__).resolve().parents[1]
FIXTURES = AI_DIR / "tests" / "fixtures" / "records"
NAMES = ("rules_2024", "mt_2025_spring_report", "ledger_2025_h1", "ledger_2024_h2")
SAMPLE_PDF = AI_DIR.parents[1] / "tests" / "fixtures" / "records" / "sample_report.pdf"

SECRETS: list[str] = []


def scrub(value: object) -> str:
    text = str(value)
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "***")
    return text


def load_fixture(name: str) -> tuple[IndexRecordRequest, StoredRecord]:
    """예시 기록 하나를 색인 요청과 메모리 port 저장용 메타데이터로 읽는다"""
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


async def run(settings: AISettings) -> dict:
    requests = 0

    async def count(request: httpx.Request) -> None:
        nonlocal requests
        requests += 1

    model = build_embeddings(
        settings, http_async_client=httpx.AsyncClient(event_hooks={"request": [count]})
    )

    async def embed(texts):
        return await aembed_texts(texts, model=model)

    result: dict = {
        "settings": {
            "embedding_model": settings.embedding_model,
            "dimensions": EMBEDDING_DIMENSIONS,
            "chunk_max_chars": CHUNK_MAX_CHARS,
            "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
            "embedding_batch_size": EMBEDDING_BATCH_SIZE,
        },
        "records": [],
    }

    print("== 색인")
    targets = [load_fixture(name)[0] for name in NAMES] + [_sample_request()]
    for request in targets:
        before, started = requests, time.perf_counter()
        indexed = await index_record_chunks(request, embed=embed)
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
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, help="결과를 JSON으로 저장할 경로")
    args = parser.parse_args()

    settings = AISettings()
    SECRETS.extend(
        [settings.api_key.get_secret_value(), settings.resolved_embedding_api_key.get_secret_value()]
    )
    settings.require_embedding()
    print(scrub(f"model={settings.embedding_model}"))

    try:
        result = asyncio.run(run(settings))
    except Exception as error:  # noqa: BLE001 - 확인 스크립트는 원인만 보여주고 끝낸다
        print(scrub(f"[FAIL] {type(error).__name__}: {error}"))
        return 1

    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"결과 저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
