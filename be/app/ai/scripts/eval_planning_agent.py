"""새 Agent의 소규모 실제 대화 검증. 설정·HTTP 헤더·원본 예외는 보고서에 넣지 않는다."""

import argparse
import asyncio
import hashlib
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from functools import partial

import httpx

from app.ai.config import AISettings
from app.ai.contracts import IndexRecordRequest
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import PROMPT_VERSION, agent_tool_schemas
from app.ai.features.planning.agent.record_tool import search_past_events
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.ai.llm import ainvoke_with_tools, ainvoke_structured, aembed_texts, build_chat_model, build_embeddings
from app.core.enums import RecordCategory


AI_DIR = Path(__file__).resolve().parents[1]
CASES = AI_DIR / "tests/fixtures/eval/planning_agent.json"


async def run(output: Path, *, cases: Path = CASES, with_records: bool = False) -> int:
    settings = AISettings()
    settings.require_api()
    if with_records: settings.require_embedding()
    cases=cases.resolve()
    dataset = json.loads(cases.read_text())
    paths = [*sorted((AI_DIR / "features/planning/agent").rglob("*.py")),
             *sorted((AI_DIR / "features/planning/agent").rglob("*.md")), AI_DIR / "llm.py", cases, Path(__file__)]
    records=sorted((AI_DIR / "tests/fixtures/records").glob("*.json")) if with_records else []
    if with_records:
        paths += records + list((AI_DIR / "features/retrieval").rglob("*.py")) + list((AI_DIR / "features/retrieval").rglob("*.md"))
    report = dict(state="RUNNING", started_at=datetime.now(timezone.utc).isoformat(),
                  model=settings.model, reasoning="provider default", prompt_version=PROMPT_VERSION,
                  with_records=with_records, embedding_model=settings.embedding_model if with_records else None,
                  review_status=dataset["review_status"], reference_date=dataset["reference_date"],
                  git_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                  git_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True)),
                  sha256={str(p.relative_to(AI_DIR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, turns=[])
    http_calls = 0
    embedding_calls = 0
    async def count_http(_):
        nonlocal http_calls
        http_calls += 1
    async def count_embedding(_):
        nonlocal embedding_calls
        embedding_calls += 1
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    save()
    async with httpx.AsyncClient(event_hooks={"request":[count_http]}) as client, httpx.AsyncClient(event_hooks={"request":[count_embedding]}) as ec:
        model = build_chat_model(settings,http_async_client=client)
        embeddings = build_embeddings(settings,http_async_client=ec) if with_records else None
        async def embed(texts): return await aembed_texts(texts,model=embeddings)
        async def structured(messages,schema): return await ainvoke_structured(messages,schema,model=model)
        async def invoke(messages, *, allow_tools):
            return await ainvoke_with_tools(messages,tools=agent_tool_schemas(search_enabled=with_records),allow_tools=allow_tools,model=model)
        memory=InMemoryRecordSearch()
        if with_records:
            started=time.perf_counter()
            try:
                chunks=0
                for path in records:
                    data=json.loads(path.read_text()); record=data["record"]
                    indexed=await index_record_chunks(IndexRecordRequest(record_id=record["id"],file_name=record["file_name"],
                        file_type=record["file_type"],blocks=data["parse_result"]["blocks"]),embed=embed)
                    memory.add(StoredRecord(record_id=record["id"],club_id=record["club_id"],file_name=record["file_name"],
                        category=RecordCategory(record["category"]),event_id=record["event_id"]),indexed.chunks)
                    chunks+=len(indexed.chunks)
            except Exception as error:
                report.update(state="INDEXING_FAILED",error_type=type(error).__name__)
                save(); print("Indexing failed:",type(error).__name__,flush=True); return 1
            report["indexing"]=dict(records=len(records),chunks=chunks,embedding_http=embedding_calls,ms=round((time.perf_counter()-started)*1000))
            save()
        for dialog in dataset["dialogs"]:
            draft = PlanningDraft(conditions=PlanningConditions.model_validate(dialog["initial"]))
            expected = draft.conditions.model_dump(mode="json")
            history = ()
            actual_port=InMemoryRecordSearch() if dialog.get("empty_records") else memory
            retrieved=set()
            class TrackedPort:
                async def search_chunks(self,query):
                    found=await actual_port.search_chunks(query)
                    retrieved.update(c.source.model_dump_json() for c in found)
                    return found
            search=partial(search_past_events,club_id="clb_keunnamu",port=TrackedPort(),embed=embed,invoke=structured) if with_records else None
            for index, case in enumerate(dialog["turns"]):
                expected.update(case["updates"])
                request = PlanningAgentTurnInput(draft=draft,history=history,
                    current_message=PlanningMessage(id=f"{dialog['id']}-user-{index}",role="user",text=case["text"]),
                    reference_date=dataset["reference_date"])
                before = request.model_dump_json()
                before_calls = http_calls
                before_embeddings = embedding_calls
                retrieved.clear()
                start = time.perf_counter()
                row = dict(dialog=dialog["id"],turn=index+1,text=case["text"],expected_conditions=dict(expected),expected=case)
                try:
                    result = await run_planning_agent_turn(request,invoke=invoke,search=search)
                except Exception as error:
                    row.update(error_type=type(error).__name__,passed=False,ms=round((time.perf_counter()-start)*1000))
                    report["turns"].append(row)
                    report.update(state="FAILED",http_calls=http_calls)
                    save()
                    print("Failed:",dialog["id"],index+1,type(error).__name__,flush=True)
                    return 1
                checks = dict(conditions=result.draft.conditions.model_dump(mode="json")==expected,
                    tool=case["tool"]=="any" or bool(result.executions)==(case["tool"]=="yes"),
                    metadata=all(result.draft.condition_meta.get(f) and result.draft.condition_meta[f].status==s for f,s in case.get("meta",{}).items()),
                    metadata_absent=all(f not in result.draft.condition_meta for f in case.get("meta_absent",[])),
                    deferral="deferred" not in case or set(result.draft.deferred_topics)==set(case["deferred"]),
                    input_preserved=request.model_dump_json()==before)
                lookup=result.record_lookup
                evidence=lookup.result if lookup else None
                facts=(*evidence.facts,*(v for c in evidence.conflicts for v in c.values)) if evidence else ()
                sources=[s for fact in facts for s in fact.sources]
                content=" ".join(f.content for f in facts).replace(",", "")
                checks.update(lookup="lookup" not in case or (lookup is not None and lookup.status==case["lookup"]),
                    evidence_terms=all(term in content for term in case.get("terms",[])),
                    expected_sources=all(any(s.record_id==record_id for s in sources) for record_id in case.get("source_records",[])),
                    sources_retrieved=all(s.model_dump_json() in retrieved for s in sources))
                # 합성 대화와 구조화된 실행 결과만 보관하고 SDK 메타정보·헤더는 제외한다.
                trace = [dict(type=m.type,content=m.content,
                              **({"tool_calls":m.tool_calls} if hasattr(m,"tool_calls") else {}))
                         for m in result.history[len(history)+1:]]
                row.update(reply=result.reply,draft=result.draft.model_dump(mode="json"),
                    executions=[e.model_dump(mode="json") for e in result.executions],trace=trace,
                    record_lookup=lookup.model_dump(mode="json") if lookup else None,
                    checks=checks,passed=all(checks.values()),model_calls=result.model_calls,
                    http_calls=http_calls-before_calls,embedding_http=embedding_calls-before_embeddings,limit_reached=result.limit_reached,
                    ms=round((time.perf_counter()-start)*1000))
                report["turns"].append(row)
                draft,history=result.draft,result.history
                save()
                print(dialog["id"],index+1,"PASS" if row["passed"] else "MISMATCH",row["ms"],"ms",flush=True)
    rows=report["turns"]
    report.update(state="COMPLETED",http_calls=http_calls,embedding_http=embedding_calls,summary=dict(turns=len(rows),passed=sum(r["passed"] for r in rows),
        median_ms=statistics.median(r["ms"] for r in rows),max_ms=max(r["ms"] for r in rows),
        model_calls=sum(r["model_calls"] for r in rows)))
    save()
    print(json.dumps(report["summary"],ensure_ascii=False),flush=True)
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",type=Path,required=True)
    parser.add_argument("--cases",type=Path,default=CASES)
    parser.add_argument("--records",action="store_true")
    args=parser.parse_args()
    raise SystemExit(asyncio.run(run(args.json,cases=args.cases,with_records=args.records)))
