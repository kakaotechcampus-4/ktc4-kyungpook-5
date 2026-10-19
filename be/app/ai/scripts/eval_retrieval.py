"""기록 검색을 평가 질문 세트로 잰다 (#99, #72).

키가 필요해 CI에서 돌리지 않는다. 검색 방식·이름표·모델을 바꿨을 때 수동으로 실행하고
결과는 docs/retrieval-evaluation.md 에 남긴다. 질문과 지표 정의는 tests/fixtures/eval/README.md 에 있다.

    cd be && uv run python app/ai/scripts/eval_retrieval.py [--search vector|records] [--max-rounds N] [--no-rewrite]
        [--header full|file|none] [--holdout] [--no-cache] [--json 결과.json]

예시 기록 12종을 색인해 메모리 port에 넣고, 질문마다 검색 함수로 청크를 받아 검색 지표를 계산한다.
--search: vector는 질문을 그대로 임베딩해 찾는 기준점, records는 기록 검색(search_records) 전체다.
          records는 결과(사실·확인하지 못한 것·자료 간 차이)를 정답과 비교한 결과 지표도 낸다
--max-rounds: records의 검색 횟수. 1이면 검색어 정리만, 2면 재검색까지 잰다
--no-rewrite: records에서 검색어 정리를 건너뛰고 질문을 그대로 검색어로 쓴다(회의 어시스턴트의 호출 방식)
records는 질문마다 구간별 시간(검색어 정리, 임베딩, 청크 검색, 근거 판단)도 남긴다
--header: 청크 임베딩에 붙이는 이름표. full 문서명·위치(현재 색인), file 문서명만, none 없음
--holdout: 확인용 질문도 잰다. 개선하는 동안에는 끄고, 기록에 남길 측정에서만 켠다.
           확인용 질문은 화면에 요약만 보이고 질문별 결과는 JSON에만 남는다
--no-cache: 임베딩·LLM 응답 캐시를 쓰지 않는다. 캐시는 같은 입력이면 저장한 값을 다시 써서
            같은 조건이면 같은 결과로 다시 잴 수 있게 한다. 캐시에서 꺼내면 걸린 시간이 실제와 달라서
            시간을 비교하거나 LLM 응답의 흔들림을 재는 측정에서는 끈다. 캐시 파일(scripts/.cache/)은 커밋하지 않는다

AI_* 는 be/.env 에서 읽는다. 출력은 scrub()을 거쳐 키가 남지 않는다.
"""

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from pathlib import Path
from statistics import mean, median

import httpx
from dotenv import load_dotenv

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import AISettings
from app.ai.errors import AIError
from app.ai.features.retrieval.chunking import (
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP_CHARS,
)
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch
from app.ai.features.retrieval.nodes import (
    ASSESS_EVIDENCE_PROMPT_VERSION,
    MAX_SEARCH_ROUNDS,
    REWRITE_QUERY_PROMPT_VERSION,
    search_records,
)
from app.ai.features.retrieval.schemas import (
    RecordFact,
    RecordSearchRequest,
    RecordSearchResult,
    SearchQueries,
)
from app.ai.llm import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    aembed_texts,
    ainvoke_structured,
    build_chat_model,
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
SEARCHES = ("vector", "records")
# records의 구간: 검색어 정리(LLM), 임베딩, 청크 검색(port), 근거 판단(LLM, 충분성 판단과 결과 구성을 한 번에)
STAGES = ("rewrite", "embed", "chunk_search", "assess")
CACHE_DIR = AI_DIR / "scripts" / ".cache"
EMBEDDING_CACHE = CACHE_DIR / "embeddings.json"
LLM_CACHE = CACHE_DIR / "llm.json"

ChunkKey = tuple[str, str]  # (record_id, location.label)
# 질문 하나로 (찾은 청크, 기록 검색 결과, 실패한 오류 이름)을 돌려주는 함수. 비교할 검색 방식마다 하나씩 만든다.
# 청크는 검색 지표에, 결과는 결과 지표에 쓴다. 기준점은 결과가 없다
SearchOutput = tuple[list[RetrievedChunk], RecordSearchResult | None, str | None]
Search = Callable[[dict], Awaitable[SearchOutput]]


def vector_search(port: InMemoryRecordSearch, embed) -> Search:
    """기준점: 질문을 그대로 임베딩해 비슷한 청크를 찾는다"""

    async def search(question: dict) -> SearchOutput:
        [vector] = await embed([question["question"]])
        found = await port.search_chunks(
            ChunkSearchQuery(club_id=CLUB_ID, embedding=vector, limit=max(KS))
        )
        return list(found), None, None

    return search


class _RecordingPort:
    """port가 돌려준 청크를 처음 나온 순서대로 모은다. 검색어가 여러 개면 검색어 순서대로 이어진다"""

    def __init__(self, inner: InMemoryRecordSearch, stages: dict[str, float]) -> None:
        self._inner = inner
        self._stages = stages
        self.chunks: list[RetrievedChunk] = []
        self._seen: set[tuple[str, str, str]] = set()

    async def search_chunks(
        self, query: ChunkSearchQuery
    ) -> tuple[RetrievedChunk, ...]:
        started = time.perf_counter()
        found = await self._inner.search_chunks(query)
        self._stages["chunk_search"] += time.perf_counter() - started
        for chunk in found:
            key = (chunk.source.record_id, chunk.source.location.label, chunk.text)
            if key not in self._seen:
                self._seen.add(key)
                self.chunks.append(chunk)
        return found


def records_search(
    port: InMemoryRecordSearch,
    embed,
    invoke,
    *,
    max_rounds: int,
    rewrite: bool,
    stages: dict[str, float],
) -> Search:
    """기록 검색(search_records) 전체. 모델 응답이 잘못돼 실패하면 실패로 센다"""

    async def search(question: dict) -> SearchOutput:
        recorder = _RecordingPort(port, stages)
        request = RecordSearchRequest(
            club_id=CLUB_ID,
            query=question["question"],
            today=date.fromisoformat(question["today"]),
            conditions=question["conditions"],
            limit=max(KS),
        )
        try:
            result = await search_records(
                request,
                port=recorder,
                embed=embed,
                invoke=invoke,
                max_rounds=max_rounds,
                rewrite=rewrite,
            )
        except AIError as error:
            return recorder.chunks, None, type(error).__name__
        return recorder.chunks, result, None

    return search


def strip_header(text: str, header: str) -> str:
    """embedding_input은 "문서: …\\n위치: …\\n\\n본문"이다. 이름표 비교 실행에서만 줄인다"""
    if header == "full":
        return text
    head, body = text.split("\n\n", 1)
    return f"{head.splitlines()[0]}\n\n{body}" if header == "file" else body


def _keys(sources) -> set[ChunkKey]:
    return {(s["record_id"], s["location"]["label"]) for s in sources}


def gold_items(question: dict) -> list[set[ChunkKey]]:
    """정답 사실·충돌 값마다 출처 청크 집합"""
    expected = question["expected"]
    items = expected["facts"] + [v for c in expected["conflicts"] for v in c["values"]]
    return [_keys(item["sources"]) for item in items]


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


def value_matches(content: str, text: str) -> bool:
    """정답 값 조각이 결과 문장에 들어 있는가. 숫자는 앞뒤 숫자까지 같아야 한다(27은 275,000에 맞지 않는다)"""
    pattern = re.escape(content)
    if content[:1].isdigit():
        pattern = r"(?<!\d)(?<!\d,)" + pattern
    if content[-1:].isdigit():
        pattern += r"(?!\d)(?!,\d)"
    return re.search(pattern, text) is not None


def _fact_keys(fact: RecordFact) -> set[ChunkKey]:
    return {(s.record_id, s.location.label) for s in fact.sources}


def _matches(item: dict, fact: RecordFact) -> bool:
    """값이 일치하고 출처가 겹치는가"""
    return value_matches(item["content"], fact.content) and bool(
        _fact_keys(fact) & _keys(item["sources"])
    )


def judge(question: dict, result: RecordSearchResult | None) -> dict:
    """결과 지표. 실패(result 없음)는 맞힌 것이 없는 결과로 센다"""
    expected = question["expected"]
    facts = result.facts if result else ()
    conflicts = result.conflicts if result else ()
    gold_records = {record_id for item in gold_items(question) for record_id, _ in item}
    return {
        "facts": len(expected["facts"]),
        "facts_hit": sum(any(_matches(e, f) for f in facts) for e in expected["facts"]),
        "result_facts": len(facts),
        # 출처가 정답 기록과 하나도 겹치지 않는 사실. 다른 연도·행사의 값을 낸 경우를 잡는다.
        # 청크 단위로 보면 같은 기록의 다른 청크에서 함께 가져온 관련 사실까지 틀린 것이 된다
        "wrong_facts": sum(
            not ({s.record_id for s in f.sources} & gold_records) for f in facts
        ),
        "not_found": bool(expected["not_found"]),
        "not_found_hit": bool(expected["not_found"])
        and bool(result and result.not_found),
        "conflicts": len(expected["conflicts"]),
        "conflicts_hit": sum(
            any(
                all(any(_matches(v, rv) for rv in rc.values) for v in c["values"])
                for rc in conflicts
            )
            for c in expected["conflicts"]
        ),
        "extra_conflict": bool(conflicts) and not expected["conflicts"],
    }


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
    summary["cache_hits"] = sum(row["cache_hits"] for row in rows)
    summary["stages"] = {
        k: {
            "avg": round(mean(row["stages"][k] for row in rows), 3),
            "p50": round(median(row["stages"][k] for row in rows), 3),
            "max": round(max(row["stages"][k] for row in rows), 3),
        }
        for k in STAGES
    }
    judged = [row["judge"] for row in rows if row["judge"] is not None]
    if judged:
        total = {key: sum(j[key] for j in judged) for key in judged[0]}
        summary["results"] = {
            "facts": f"{total['facts_hit']}/{total['facts']}",
            "wrong_facts": f"{total['wrong_facts']}/{total['result_facts']}",
            "not_found": f"{total['not_found_hit']}/{total['not_found']}",
            "conflicts": f"{total['conflicts_hit']}/{total['conflicts']}",
            "extra_conflicts": total["extra_conflict"],
            "failures": sum(row["error"] is not None for row in rows),
            "llm_requests": sum(row["llm_requests"] for row in rows),
            "llm_cache_hits": sum(row["llm_cache_hits"] for row in rows),
        }
    return summary


def _hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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


def _counting_client(counter: list[int]) -> httpx.AsyncClient:
    async def count(request: httpx.Request) -> None:
        counter[0] += 1

    return httpx.AsyncClient(event_hooks={"request": [count]})


async def run(
    settings: AISettings,
    *,
    search_name: str,
    max_rounds: int,
    rewrite: bool,
    header: str,
    holdout: bool,
    use_cache: bool,
) -> dict:
    # 실제로 API에 보낸 요청 수와 캐시에서 꺼낸 수
    embed_requests, llm_requests = [0], [0]
    embed_hits, llm_hits = [0], [0]
    # 구간별 누적 시간(초). 질문마다 앞뒤 차이로 그 질문의 구간 시간을 낸다
    stages = dict.fromkeys(STAGES, 0.0)

    embeddings = build_embeddings(
        settings, http_async_client=_counting_client(embed_requests)
    )
    embed_cache = _load(EMBEDDING_CACHE) if use_cache else None

    async def embed(texts):
        started = time.perf_counter()
        try:
            return await _embed(texts)
        finally:
            stages["embed"] += time.perf_counter() - started

    async def _embed(texts):
        if embed_cache is None:
            return await aembed_texts(texts, model=embeddings)
        keys = [
            _hash(settings.embedding_model, str(EMBEDDING_DIMENSIONS), t) for t in texts
        ]
        missing = list(
            dict.fromkeys(
                t for t, k in zip(texts, keys, strict=True) if k not in embed_cache
            )
        )
        if missing:
            vectors = await aembed_texts(missing, model=embeddings)
            for text, vector in zip(missing, vectors, strict=True):
                embed_cache[
                    _hash(settings.embedding_model, str(EMBEDDING_DIMENSIONS), text)
                ] = list(vector)
        embed_hits[0] += len(texts) - len(missing)
        return [tuple(embed_cache[key]) for key in keys]

    async def embed_chunks(texts):
        return await embed([strip_header(text, header) for text in texts])

    llm_cache = _load(LLM_CACHE) if use_cache else None
    chat = (
        build_chat_model(settings, http_async_client=_counting_client(llm_requests))
        if search_name == "records"
        else None
    )

    async def invoke(messages, schema):
        started = time.perf_counter()
        try:
            return await _invoke(messages, schema)
        finally:
            stage = "rewrite" if schema is SearchQueries else "assess"
            stages[stage] += time.perf_counter() - started

    async def _invoke(messages, schema):
        key = _hash(
            settings.model,
            json.dumps(schema.model_json_schema(), ensure_ascii=False, sort_keys=True),
            *(f"{m.type}\n{m.content}" for m in messages),
        )
        if llm_cache is not None and key in llm_cache:
            llm_hits[0] += 1
            return schema.model_validate(llm_cache[key])
        output = await ainvoke_structured(messages, schema, model=chat)
        if llm_cache is not None:
            llm_cache[key] = output.model_dump(mode="json")
        return output

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
        "requests": embed_requests[0],
        "cache_hits": embed_hits[0],
        "seconds": round(time.perf_counter() - started, 2),
    }
    print(
        f"== 색인: 기록 {index['records']}종 → 청크 {chunks}개, "
        f"요청 {index['requests']}회, {index['seconds']}초"
    )

    # 검색
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if not holdout:
        questions = [q for q in questions if q["split"] == "dev"]
    search = (
        records_search(
            port, embed, invoke, max_rounds=max_rounds, rewrite=rewrite, stages=stages
        )
        if search_name == "records"
        else vector_search(port, embed)
    )
    rows = []
    print(f"\n== 검색 ({search_name}, 개발용 질문만 질문별로 보인다)")
    for question in questions:
        before = (embed_requests[0], embed_hits[0], llm_requests[0], llm_hits[0])
        stages_before = dict(stages)
        started = time.perf_counter()
        found, result, error = await search(question)
        seconds = time.perf_counter() - started
        ranked = [(c.source.record_id, c.source.location.label) for c in found]
        row = {
            "id": question["id"],
            "split": question["split"],
            "requirement": question["requirement"],
            "question": question["question"],
            "seconds": round(seconds, 2),
            "stages": {k: round(stages[k] - stages_before[k], 3) for k in STAGES},
            "requests": embed_requests[0] - before[0],
            "cache_hits": embed_hits[0] - before[1],
            "llm_requests": llm_requests[0] - before[2],
            "llm_cache_hits": llm_hits[0] - before[3],
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
            "result": result.model_dump(mode="json") if result else None,
            "error": error,
            "judge": judge(question, result) if search_name == "records" else None,
        }
        rows.append(row)
        if question["split"] == "dev":
            _print_row(row)

    groups = {
        split: summarize([r for r in rows if r["split"] == split])
        for split in ("dev", "holdout")
        if any(r["split"] == split for r in rows)
    }
    for requirement in sorted({r["requirement"] for r in rows}):
        groups[requirement] = summarize(
            [r for r in rows if r["requirement"] == requirement]
        )
    _print_summary(groups, header=header, search_name=search_name)
    print(
        f"임베딩 요청: 색인 {index['requests']}회, 검색 {embed_requests[0] - index['requests']}회. "
        f"캐시에서 꺼낸 글: 색인 {index['cache_hits']}개, 검색 {embed_hits[0] - index['cache_hits']}개"
    )
    if search_name == "records":
        print(f"LLM 요청: {llm_requests[0]}회, 캐시에서 꺼낸 응답 {llm_hits[0]}개")
        print("구간별 시간 (질문당 평균 / 중앙 / 최대 초):")
        for name, s in groups.items():
            if name in ("dev", "holdout"):
                print(
                    f"  {name:<8} "
                    + "  ".join(
                        f"{k} {v['avg']:.2f}/{v['p50']:.2f}/{v['max']:.2f}"
                        for k, v in s["stages"].items()
                    )
                )

    if embed_cache is not None:
        _save(EMBEDDING_CACHE, embed_cache)
    if llm_cache is not None:
        _save(LLM_CACHE, llm_cache)

    return {
        "settings": {
            **_git(),
            "embedding_model": settings.embedding_model,
            "dimensions": EMBEDDING_DIMENSIONS,
            "chunk_max_chars": CHUNK_MAX_CHARS,
            "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
            "embedding_batch_size": EMBEDDING_BATCH_SIZE,
            "embedding_header": header,
            "search": search_name,
            "chat_model": settings.model if search_name == "records" else None,
            "max_rounds": max_rounds if search_name == "records" else None,
            "rewrite": rewrite if search_name == "records" else None,
            "prompt_versions": (
                {"rewrite": REWRITE_QUERY_PROMPT_VERSION, "assess": ASSESS_EVIDENCE_PROMPT_VERSION}
                if search_name == "records"
                else None
            ),
            "limit": max(KS),
            "holdout": holdout,
            "cache": use_cache,
        },
        "index": index,
        "summary": groups,
        "questions": rows,
    }


def _print_row(row: dict) -> None:
    first = row["metrics"]["first_rank"] if row["metrics"] else None
    mark = (
        "정답 청크 없음"
        if not row["metrics"]
        else (f"{first}위" if first else "못 찾음")
    )
    print(f"- {row['id']} [{mark}] {row['question']}")
    j = row["judge"]
    if j is None:
        top1 = row["top"][0] if row["top"] else None
        print(
            f"    1위: {top1['file_name']} · {top1['label']} ({top1['score']:.3f})"
            if top1
            else "    1위: -"
        )
        return
    if row["error"]:
        print(f"    실패: {row['error']}")
        return
    parts = [
        f"사실 {j['facts_hit']}/{j['facts']}",
        f"틀린 사실 {j['wrong_facts']}/{j['result_facts']}",
    ]
    if j["not_found"]:
        parts.append(f"없음 {'O' if j['not_found_hit'] else 'X'}")
    if j["conflicts"]:
        parts.append(f"충돌 {j['conflicts_hit']}/{j['conflicts']}")
    if j["extra_conflict"]:
        parts.append("없는 충돌")
    parts.append(f"{row['seconds']}초")
    print("    " + " · ".join(parts))


def _print_summary(groups: dict, *, header: str, search_name: str) -> None:
    print(f"\n== 검색 지표 (search={search_name}, header={header})")
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
    if search_name != "records":
        return
    print("\n== 결과 지표 (맞힌 수/전체)")
    print(
        "구분            사실     틀린 사실  없음    충돌   없는 충돌  실패  LLM 요청"
    )
    for name, s in groups.items():
        r = s["results"]
        print(
            f"{name:<14} {r['facts']:>7} {r['wrong_facts']:>9} {r['not_found']:>6} "
            f"{r['conflicts']:>6} {r['extra_conflicts']:>9} {r['failures']:>5} {r['llm_requests']:>8}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--search", choices=SEARCHES, default="vector", help="검색 방식"
    )
    parser.add_argument(
        "--max-rounds", type=int, default=MAX_SEARCH_ROUNDS, help="records의 검색 횟수"
    )
    parser.add_argument(
        "--no-rewrite", action="store_true", help="records에서 검색어 정리를 건너뛴다"
    )
    parser.add_argument(
        "--header", choices=HEADERS, default="full", help="청크 임베딩 이름표"
    )
    parser.add_argument("--holdout", action="store_true", help="확인용 질문도 잰다")
    parser.add_argument(
        "--no-cache", action="store_true", help="임베딩·LLM 캐시를 쓰지 않는다"
    )
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
    if args.search == "records":
        settings.require_api()
    print(
        scrub(
            f"search={args.search} max_rounds={args.max_rounds} rewrite={not args.no_rewrite} "
            f"header={args.header} "
            f"holdout={args.holdout} cache={not args.no_cache}"
        )
    )

    try:
        result = asyncio.run(
            run(
                settings,
                search_name=args.search,
                max_rounds=args.max_rounds,
                rewrite=not args.no_rewrite,
                header=args.header,
                holdout=args.holdout,
                use_cache=not args.no_cache,
            )
        )
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
