"""실제 모델로 내부 한 턴을 실행한다. be/에서 -m ... --json 결과경로.

기대값은 실행 전 고정한 합성 대화다. 응답 불일치도 실제 상태로 이어가고,
예외 발생 시 해당 대화의 나머지 턴은 SKIPPED로 기록한다. 캐시는 사용하지 않는다.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import httpx

from app.ai.config import AISettings
from app.ai.contracts import IndexRecordRequest
from app.ai.features.planning.lookup import LOOKUP_PROMPT_VERSION, RecordLookupDecision
from app.ai.features.planning.nodes import PROMPT_VERSION
from app.ai.features.planning.schemas import ConditionExtractionOutput, PlanningConditions
from app.ai.features.planning.turn_flow import process_planning_turn
from app.ai.features.planning.turn_schemas import PlanningTurnInput
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.features.retrieval.nodes import ASSESS_EVIDENCE_PROMPT_VERSION, REWRITE_QUERY_PROMPT_VERSION
from app.ai.llm import aembed_texts, ainvoke_structured, build_chat_model, build_embeddings
from app.core.enums import RecordCategory

AI_DIR = Path(__file__).resolve().parents[1]
CASES = AI_DIR / "tests/fixtures/eval/planning_turns.json"


async def run(output):
    # AISettings만 .env를 읽는다. import 시 환경 변수를 바꾸는 기존 평가 스크립트는 사용하지 않는다.
    settings = AISettings(); settings.require_api(); settings.require_embedding()
    dataset = json.loads(CASES.read_text())
    counts = dict(chat_http=0, embedding_http=0, port=0)
    paths = list((AI_DIR / "features").rglob("*.py")) + list((AI_DIR / "features").rglob("*.md"))
    records = sorted((AI_DIR / "tests/fixtures/records").glob("*.json"))
    paths += records + [CASES, Path(__file__)]
    report = dict(state="RUNNING", started_at=datetime.now(timezone.utc).isoformat(),
                  model=settings.model, embedding_model=settings.embedding_model,
                  reasoning="provider default", cache=False,
                  git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                  git_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
                  review_status=dataset["review_status"],
                  prompt_versions=[PROMPT_VERSION, LOOKUP_PROMPT_VERSION, REWRITE_QUERY_PROMPT_VERSION, ASSESS_EVIDENCE_PROMPT_VERSION],
                  sha256={str(p.relative_to(AI_DIR)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  planned_turns=sum(len(d["turns"]) for d in dataset["dialogs"]), turns=[])

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    async def count_chat(_): counts["chat_http"] += 1
    async def count_embedding(_): counts["embedding_http"] += 1

    async with httpx.AsyncClient(event_hooks={"request": [count_chat]}) as cc, httpx.AsyncClient(event_hooks={"request": [count_embedding]}) as ec:
        model = build_chat_model(settings, http_async_client=cc)
        embeddings = build_embeddings(settings, http_async_client=ec)

        async def embed(texts): return await aembed_texts(texts, model=embeddings)
        memory = InMemoryRecordSearch()
        start = time.perf_counter()
        try:
            total_chunks = 0
            for path in records:
                data = json.loads(path.read_text()); r = data["record"]
                indexed = await index_record_chunks(IndexRecordRequest(record_id=r["id"], file_name=r["file_name"],
                    file_type=r["file_type"], blocks=data["parse_result"]["blocks"]), embed=embed)
                memory.add(StoredRecord(record_id=r["id"], club_id=r["club_id"], file_name=r["file_name"],
                    category=RecordCategory(r["category"]), event_id=r["event_id"]), indexed.chunks)
                total_chunks += len(indexed.chunks)
        except Exception as error:
            report.update(state="INDEXING_FAILED", error_type=type(error).__name__, calls=counts)
            save(); print("Indexing failed:", type(error).__name__, flush=True); return 1
        report["indexing"] = dict(records=len(records), chunks=total_chunks, ms=round((time.perf_counter()-start)*1000), calls=dict(counts))
        save()
        for dialog in dataset["dialogs"]:
            conditions = PlanningConditions.model_validate(dialog["initial"])
            expected_conditions = conditions.model_dump(mode="json")
            event_id = "eval-" + dialog["id"]
            state = {"event_id": event_id}; pending = []; context = []; failed = False
            for index, turn in enumerate(dialog["turns"]):
                if failed:
                    report["turns"].append(dict(dialog=dialog["id"], turn=index+1, state="SKIPPED", passed=False))
                    save(); continue
                expected_conditions.update(turn["updates"])
                message_id = f"{dialog['id']}-user-{index}"
                req = PlanningTurnInput.model_validate(dict(club_id="clb_keunnamu", question_state=state,
                    pending_clarifications=pending, extraction_input=dict(event_id=event_id,
                        request_id=f"{event_id}-{index}", base_version=index, conditions=conditions,
                        current_message=dict(id=message_id, role="user", text=turn["text"]), context_messages=context,
                        reference_date=dataset["reference_date"], timezone=dataset["timezone"])))
                before = req.model_dump(); trace = []; retrieved = set(); before_counts = dict(counts)

                async def invoke(messages, schema):
                    answer = await ainvoke_structured(messages, schema, model=model)
                    trace.append(dict(schema=schema.__name__, output=answer.model_dump(mode="json")))
                    return answer
                async def extract(messages): return await invoke(messages, ConditionExtractionOutput)
                async def decide(messages): return await invoke(messages, RecordLookupDecision)
                class Port:
                    async def search_chunks(self, query):
                        counts["port"] += 1
                        chunks = await memory.search_chunks(query)
                        retrieved.update(c.source.model_dump_json() for c in chunks)
                        return chunks

                row = dict(dialog=dialog["id"], turn=index+1, input=req.model_dump(mode="json"), expected=turn,
                           expected_conditions=dict(expected_conditions))
                start = time.perf_counter()
                try:
                    result = await process_planning_turn(req, port=Port(), extract=extract, decide=decide, embed=embed, invoke=invoke)
                    lookup = next(t["output"]["action"] for t in trace if t["schema"] == "RecordLookupDecision")
                    sources = []
                    if result.record_lookup.result:
                        found = result.record_lookup.result
                        sources += [s for f in found.cards for s in f.sources]
                        sources += [s for c in found.conflicts for f in c.values for s in f.sources]
                    checks = dict(action=lookup == turn["action"],
                        conditions=result.collected.model_dump(mode="json") == expected_conditions,
                        pending=[p.item.field for p in result.pending_clarifications] == turn["pending"],
                        question_fields=(list(result.question.fields) if result.question else None) == turn["question_fields"],
                        ready=result.readiness.ready_to_generate == turn["ready"], input_unchanged=req.model_dump()==before,
                        sources_retrieved=all(s.model_dump_json() in retrieved for s in sources),
                        lookup_status=result.record_lookup.status == {"SKIP":"SKIPPED", "CLARIFY":"NEEDS_CLARIFICATION", "SEARCH":"SUCCEEDED"}[turn["action"]])
                    row.update(state="RETURNED", checks=checks, passed=all(checks.values()), result=result.model_dump(mode="json"))
                    # 기대값으로 고치지 않고 실제 응답 상태를 다음 턴에 넘긴다.
                    conditions=result.collected; state=result.next_question_state; pending=result.pending_clarifications
                    context.extend([req.extraction_input.current_message.model_dump(mode="json"),
                        dict(id=f"{dialog['id']}-assistant-{index}", role="assistant", text=result.reply)])
                except Exception as error:
                    row.update(state="ERROR", error_type=type(error).__name__, passed=False)
                    failed=True
                row.update(trace=trace, ms=round((time.perf_counter()-start)*1000), calls={k:counts[k]-before_counts[k] for k in counts})
                report["turns"].append(row); save()
                print(f"{dialog['id']}:{index+1} {row['state']} {'PASS' if row['passed'] else 'FAIL'} {row['ms']}ms", flush=True)
    executed=[r for r in report["turns"] if r["state"] != "SKIPPED"]
    report.update(state="COMPLETED", calls=counts, summary=dict(planned=report["planned_turns"],
        executed=len(executed), passed=sum(r["passed"] for r in report["turns"]),
        errors=sum(r["state"]=="ERROR" for r in executed), skipped=report["planned_turns"]-len(executed),
        median_ms=median(r["ms"] for r in executed), max_ms=max(r["ms"] for r in executed)))
    save(); print(json.dumps(report["summary"]), flush=True)
    return 0 if report["summary"]["passed"] == report["planned_turns"] else 1


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    args=parser.parse_args()
    raise SystemExit(asyncio.run(run(args.json)))
