"""기록 검색을 평가 질문 세트로 잰다 (#99).

키가 필요해 CI에서 돌리지 않는다. 검색 방식·이름표·모델을 바꿨을 때 수동으로 실행하고
결과는 docs/retrieval-evaluation.md 에 남긴다. 질문과 지표 정의는 tests/fixtures/eval/README.md 에 있다.

    cd be && uv run python app/ai/scripts/eval_retrieval.py [--header full|file|none] [--holdout] [--json 결과.json]

예시 기록 12종을 색인해 메모리 port에 넣고, 질문마다 검색 함수로 상위 청크를 받아 검색 지표를 계산한다.
--header: 청크 임베딩에 붙이는 이름표. full 문서명·위치(현재 색인), file 문서명만, none 없음
--holdout: 확인용 질문도 잰다. 개선하는 동안에는 끄고, 기록에 남길 측정에서만 켠다.
           확인용 질문은 화면에 요약만 보이고 질문별 결과는 JSON에만 남는다

AI_* 는 be/.env 에서 읽는다. 출력은 scrub()을 거쳐 키가 남지 않는다.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from statistics import mean

import httpx
from dotenv import load_dotenv

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import AISettings
from app.ai.features.retrieval.chunking import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
)
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch
from app.ai.llm import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    aembed_texts,
    build_embeddings,
)
from app.ai.ports import ChunkSearchQuery, RetrievedChunk
from app.ai.scripts.check_index_record import (
    AI_DIR,
    FIXTURES,
    SECRETS,
    load_fixture,
    scrub,
)

QUESTIONS = AI_DIR / "tests" / "fixtures" / "eval" / "questions.json"
CLUB_ID = "clb_keunnamu"
KS = (1, 3, 5)
HEADERS = ("full", "file", "none")

# 질문 하나로 청크를 유사도 높은 순서로 찾는 함수. 비교할 검색 방식마다 하나씩 만든다
Search = Callable[[dict], Awaitable[Sequence[RetrievedChunk]]]
ChunkKey = tuple[str, str]  # (record_id, location.label)


def vector_search(port: InMemoryRecordSearch, embed) -> Search:
    """기준점: 질문을 그대로 임베딩해 비슷한 청크를 찾는다"""

    async def search(question: dict) -> Sequence[RetrievedChunk]:
        [vector] = await embed([question["question"]])
        return await port.search_chunks(
            ChunkSearchQuery(club_id=CLUB_ID, embedding=vector, limit=max(KS))
        )

    return search


def strip_header(text: str, header: str) -> str:
    """embedding_input은 "문서: …\\n위치: …\\n\\n본문"이다. 이름표 비교 실행에서만 줄인다"""
    if header == "full":
        return text
    head, body = text.split("\n\n", 1)
    return f"{head.splitlines()[0]}\n\n{body}" if header == "file" else body


def gold_items(question: dict) -> list[set[ChunkKey]]:
    """정답 사실·충돌 값마다 출처 청크 집합"""
    expected = question["expected"]
    items = expected["facts"] + [v for c in expected["conflicts"] for v in c["values"]]
    return [
        {(s["record_id"], s["location"]["label"]) for s in item["sources"]}
        for item in items
    ]


def score(question: dict, ranked: Sequence[ChunkKey]) -> dict | None:
    """검색 지표. 정답 청크가 없는 질문(관련 기록 없음)은 None"""
    items = gold_items(question)
    if not items:
        return None
    gold = set().union(*items)
    first = next((rank for rank, key in enumerate(ranked, 1) if key in gold), None)
    metrics = {"first_rank": first, "rr": 1 / first if first else 0.0}
    for k in KS:
        top = set(ranked[:k])
        metrics[f"hit@{k}"] = float(first is not None and first <= k)
        metrics[f"recall@{k}"] = sum(bool(item & top) for item in items) / len(items)
    return metrics


def summarize(rows: list[dict]) -> dict:
    scored = [row["metrics"] for row in rows if row["metrics"]]
    summary: dict = {"questions": len(rows), "scored": len(scored)}
    if scored:
        summary["mrr"] = round(mean(m["rr"] for m in scored), 3)
        for k in KS:
            summary[f"hit@{k}"] = round(mean(m[f"hit@{k}"] for m in scored), 3)
            summary[f"recall@{k}"] = round(mean(m[f"recall@{k}"] for m in scored), 3)
    summary["seconds_avg"] = round(mean(row["seconds"] for row in rows), 2)
    summary["seconds_max"] = round(max(row["seconds"] for row in rows), 2)
    summary["requests"] = sum(row["requests"] for row in rows)
    return summary


def _git() -> dict:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


async def run(settings: AISettings, *, header: str, holdout: bool) -> dict:
    requests = 0

    async def count(request: httpx.Request) -> None:
        nonlocal requests
        requests += 1

    model = build_embeddings(
        settings, http_async_client=httpx.AsyncClient(event_hooks={"request": [count]})
    )

    async def embed(texts):
        return await aembed_texts(texts, model=model)

    async def embed_chunks(texts):
        return await embed([strip_header(text, header) for text in texts])

    # 색인
    port = InMemoryRecordSearch()
    started, chunks = time.perf_counter(), 0
    for path in sorted(FIXTURES.glob("*.json")):
        request, stored = load_fixture(path.stem)
        indexed = await index_record_chunks(request, embed=embed_chunks)
        port.add(stored, indexed.chunks)
        chunks += len(indexed.chunks)
    index = {
        "records": len(list(FIXTURES.glob("*.json"))),
        "chunks": chunks,
        "requests": requests,
        "seconds": round(time.perf_counter() - started, 2),
    }
    print(
        f"== 색인: 기록 {index['records']}종 → 청크 {chunks}개, 요청 {requests}회, {index['seconds']}초"
    )

    # 검색
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if not holdout:
        questions = [q for q in questions if q["split"] == "dev"]
    search = vector_search(port, embed)
    rows = []
    print(f"\n== 검색 (상위 {max(KS)}개, 개발용 질문만 질문별로 보인다)")
    for question in questions:
        before, started = requests, time.perf_counter()
        found = await search(question)
        seconds = time.perf_counter() - started
        ranked = [(c.source.record_id, c.source.location.label) for c in found]
        row = {
            "id": question["id"],
            "split": question["split"],
            "requirement": question["requirement"],
            "question": question["question"],
            "seconds": round(seconds, 2),
            "requests": requests - before,
            "top": [
                {
                    "record_id": c.source.record_id,
                    "file_name": c.source.file_name,
                    "label": c.source.location.label,
                    "score": round(c.score, 4),
                }
                for c in found
            ],
            "metrics": score(question, ranked),
        }
        rows.append(row)
        if question["split"] == "dev":
            first = row["metrics"]["first_rank"] if row["metrics"] else None
            mark = (
                "정답 없음"
                if not row["metrics"]
                else (f"{first}위" if first else f"{max(KS)}위 밖")
            )
            top1 = row["top"][0] if row["top"] else None
            top1_text = (
                f"{top1['file_name']} · {top1['label']} ({top1['score']:.3f})"
                if top1
                else "-"
            )
            print(f"- {row['id']} [{mark}] {row['question']}\n    1위: {top1_text}")

    groups = {
        split: summarize([r for r in rows if r["split"] == split])
        for split in ("dev", "holdout")
        if any(r["split"] == split for r in rows)
    }
    for requirement in sorted({r["requirement"] for r in rows}):
        groups[requirement] = summarize(
            [r for r in rows if r["requirement"] == requirement]
        )

    print(f"\n== 요약 (header={header})")
    print(
        "구분            질문 채점  Hit@1 Hit@3 Hit@5   MRR   R@1   R@3   R@5  평균초"
    )
    for name, s in groups.items():
        metrics = (
            f"{s['hit@1']:5.2f} {s['hit@3']:5.2f} {s['hit@5']:5.2f} {s['mrr']:5.2f} "
            f"{s['recall@1']:5.2f} {s['recall@3']:5.2f} {s['recall@5']:5.2f}"
            if s["scored"]
            else "  -" + " " * 39
        )
        print(
            f"{name:<14} {s['questions']:4} {s['scored']:4}  {metrics} {s['seconds_avg']:6.2f}"
        )
    print(
        f"임베딩 요청: 색인 {index['requests']}회, 검색 {requests - index['requests']}회"
    )

    return {
        "settings": {
            **_git(),
            "embedding_model": settings.embedding_model,
            "dimensions": EMBEDDING_DIMENSIONS,
            "chunk_max_chars": CHUNK_MAX_CHARS,
            "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
            "embedding_batch_size": EMBEDDING_BATCH_SIZE,
            "embedding_header": header,
            "search": "vector",
            "limit": max(KS),
            "holdout": holdout,
        },
        "index": index,
        "summary": groups,
        "questions": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--header", choices=HEADERS, default="full", help="청크 임베딩 이름표"
    )
    parser.add_argument("--holdout", action="store_true", help="확인용 질문도 잰다")
    parser.add_argument("--json", type=Path, help="결과를 JSON으로 저장할 경로")
    args = parser.parse_args()

    settings = AISettings()
    SECRETS.extend(
        [
            settings.api_key.get_secret_value(),
            settings.resolved_embedding_api_key.get_secret_value(),
        ]
    )
    settings.require_embedding()
    print(
        scrub(
            f"model={settings.embedding_model} header={args.header} holdout={args.holdout}"
        )
    )

    try:
        result = asyncio.run(run(settings, header=args.header, holdout=args.holdout))
    except Exception as error:  # noqa: BLE001 - 확인 스크립트는 원인만 보여주고 끝낸다
        print(scrub(f"[FAIL] {type(error).__name__}: {error}"))
        return 1

    if args.json:
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"결과 저장: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
