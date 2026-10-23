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

import httpx

from app.ai.config import AISettings
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import PROMPT_VERSION, condition_tool_schema
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage
from app.ai.llm import ainvoke_with_tools, build_chat_model


AI_DIR = Path(__file__).resolve().parents[1]
CASES = AI_DIR / "tests/fixtures/eval/planning_agent.json"


async def run(output: Path) -> int:
    settings = AISettings()
    settings.require_api()
    dataset = json.loads(CASES.read_text())
    paths = [*sorted((AI_DIR / "features/planning/agent").rglob("*.py")),
             *sorted((AI_DIR / "features/planning/agent").rglob("*.md")), AI_DIR / "llm.py", CASES, Path(__file__)]
    report = dict(state="RUNNING", started_at=datetime.now(timezone.utc).isoformat(),
                  model=settings.model, reasoning="provider default", prompt_version=PROMPT_VERSION,
                  review_status=dataset["review_status"], reference_date=dataset["reference_date"],
                  git_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                  git_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True)),
                  sha256={str(p.relative_to(AI_DIR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, turns=[])
    http_calls = 0
    async def count_http(_):
        nonlocal http_calls
        http_calls += 1
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    save()
    async with httpx.AsyncClient(event_hooks={"request":[count_http]}) as client:
        model = build_chat_model(settings,http_async_client=client)
        async def invoke(messages, *, allow_tools):
            return await ainvoke_with_tools(messages,tools=[condition_tool_schema()],allow_tools=allow_tools,model=model)
        for dialog in dataset["dialogs"]:
            draft = PlanningDraft(conditions=PlanningConditions.model_validate(dialog["initial"]))
            expected = draft.conditions.model_dump(mode="json")
            history = ()
            for index, case in enumerate(dialog["turns"]):
                expected.update(case["updates"])
                request = PlanningAgentTurnInput(draft=draft,history=history,
                    current_message=PlanningMessage(id=f"{dialog['id']}-user-{index}",role="user",text=case["text"]),
                    reference_date=dataset["reference_date"])
                before = request.model_dump_json()
                before_calls = http_calls
                start = time.perf_counter()
                row = dict(dialog=dialog["id"],turn=index+1,text=case["text"],expected_conditions=dict(expected),expected=case)
                try:
                    result = await run_planning_agent_turn(request,invoke=invoke)
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
                # 합성 대화와 구조화된 실행 결과만 보관하고 SDK 메타정보·헤더는 제외한다.
                trace = [dict(type=m.type,content=m.content,
                              **({"tool_calls":m.tool_calls} if hasattr(m,"tool_calls") else {}))
                         for m in result.history[len(history)+1:]]
                row.update(reply=result.reply,draft=result.draft.model_dump(mode="json"),
                    executions=[e.model_dump(mode="json") for e in result.executions],trace=trace,
                    checks=checks,passed=all(checks.values()),model_calls=result.model_calls,
                    http_calls=http_calls-before_calls,limit_reached=result.limit_reached,
                    ms=round((time.perf_counter()-start)*1000))
                report["turns"].append(row)
                draft,history=result.draft,result.history
                save()
                print(dialog["id"],index+1,"PASS" if row["passed"] else "MISMATCH",row["ms"],"ms",flush=True)
    rows=report["turns"]
    report.update(state="COMPLETED",http_calls=http_calls,summary=dict(turns=len(rows),passed=sum(r["passed"] for r in rows),
        median_ms=statistics.median(r["ms"] for r in rows),max_ms=max(r["ms"] for r in rows),
        model_calls=sum(r["model_calls"] for r in rows)))
    save()
    print(json.dumps(report["summary"],ensure_ascii=False),flush=True)
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",type=Path,required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args().json)))
