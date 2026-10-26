"""계획 생성의 채팅/버튼 실제 모델 검증. 입력·기대값은 실행 전에 고정한다."""

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
from pydantic import ValidationError

from app.ai.config import AISettings
from app.ai.errors import AIInvalidResponseError
from app.ai.features.planning.agent.generation_tools import latest_reference_facts, plan_messages
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import PROMPT_VERSION, agent_tool_schemas
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.generation.entrypoints import ButtonPlanGenerationRequest, run_button_plan_generation
from app.ai.features.planning.generation.graph import PROMPT_VERSION as GENERATION_VERSION, run_plan_generation, validate_plan
from app.ai.features.planning.generation.model import PLAN_MAX_OUTPUT_TOKENS, build_plan_model
from app.ai.features.planning.generation.schemas import PlanningGenerationState
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage
from app.ai.llm import ainvoke_structured, ainvoke_with_tools, build_chat_model


AI_DIR = Path(__file__).resolve().parents[1]
CASES = AI_DIR / "tests/fixtures/eval/planning_generation.json"


async def run(output: Path, *, dialog_id: str | None = None) -> int:
    settings=AISettings(); settings.require_api()
    dataset=json.loads(CASES.read_text())
    if dialog_id:
        dataset["dialogs"]=[x for x in dataset["dialogs"] if x["id"]==dialog_id]
        if not dataset["dialogs"]: raise ValueError("알 수 없는 dialog ID")
    paths=[*sorted((AI_DIR/"features/planning/agent").rglob("*.py")),
           *sorted((AI_DIR/"features/planning/agent").rglob("*.md")),
           *sorted((AI_DIR/"features/planning/generation").rglob("*.py")),
           *sorted((AI_DIR/"features/planning/generation").rglob("*.md")),AI_DIR/"llm.py",CASES,Path(__file__)]
    report=dict(state="RUNNING",started_at=datetime.now(timezone.utc).isoformat(),model=settings.model,
        reasoning="provider default",generation_max_output_tokens=PLAN_MAX_OUTPUT_TOKENS,
        prompt_version=PROMPT_VERSION,generation_prompt_version=GENERATION_VERSION,
        review_status=dataset["review_status"],reference_date=dataset["reference_date"],dialog_filter=dialog_id,
        git_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        git_dirty=bool(subprocess.check_output(["git","status","--porcelain"],text=True)),
        sha256={str(p.relative_to(AI_DIR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},turns=[])
    http_calls=0
    async def count(_):
        nonlocal http_calls
        http_calls+=1
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    save()
    async with httpx.AsyncClient(event_hooks={"request":[count]}) as client:
        model=build_chat_model(settings,http_async_client=client)
        generation_model=build_plan_model(settings,http_async_client=client)
        compositions=[]
        validation_reasons=[]
        provider_errors=[]
        schema_errors=[]
        async def invoke(messages, *, allow_tools):
            return await ainvoke_with_tools(messages,tools=agent_tool_schemas(search_enabled=False,generation_enabled=True),
                                            allow_tools=allow_tools,model=model)
        async def generate(request):
            captured=[]
            async def structured(messages,schema):
                try:
                    answer=await ainvoke_structured(messages,schema,model=generation_model)
                except Exception as error:
                    provider_errors.append(type(error).__name__)
                    cause=error.__cause__
                    for _ in range(4):
                        if cause is None: break
                        if isinstance(cause,ValidationError):
                            schema_errors.extend(dict(type=e["type"],field=list(e["loc"]))
                                for e in cause.errors(include_input=False,include_url=False))
                        cause=cause.__cause__
                    raise
                captured.append(answer);compositions.append(answer.model_dump(mode="json"))
                return answer
            result=await run_plan_generation(request,invoke=structured)
            if result.status=="failed" and captured:
                # 호출에 성공한 구조화 초안만 재검사해 코드의 검증 이유를 기록한다. 공급자 오류 원문은 기록하지 않는다.
                try: validate_plan(dict(request=request,composition=captured[-1]))
                except AIInvalidResponseError as error: validation_reasons.append(str(error))
            return result
        for dialog in dataset["dialogs"]:
            draft=PlanningDraft(conditions=PlanningConditions.model_validate(dialog["initial"]))
            expected=draft.conditions.model_dump(mode="json")
            generation=PlanningGenerationState();history=()
            for i,case in enumerate(dialog["turns"],1):
                expected.update(case["updates"])
                row=dict(dialog=dialog["id"],turn=i,case=case)
                compositions.clear();validation_reasons.clear();provider_errors.clear();schema_errors.clear()
                before_http=http_calls;started=time.perf_counter()
                try:
                    if case["source"]=="chat":
                        request=PlanningAgentTurnInput(draft=draft,history=history,generation=generation,
                            current_message=PlanningMessage(id=f"{dialog['id']}-{i}",role="user",text=case["text"]),
                            reference_date=dataset["reference_date"])
                        before=request.model_dump_json()
                        result=await run_planning_agent_turn(request,invoke=invoke,generate=generate)
                        checks=dict(input_preserved=request.model_dump_json()==before)
                        trace=[dict(type=m.type,content=m.text,**({"tool_calls":m.tool_calls} if hasattr(m,"tool_calls") else {}))
                               for m in result.history[len(history)+1:]]
                        draft,history,generation=result.draft,result.history,result.generation
                        outcome=result.generation_result
                        row.update(reply=result.reply,trace=trace,agent_calls=result.model_calls,generation_calls=result.generation_model_calls,
                                   limit_reached=result.limit_reached)
                    else:
                        request=ButtonPlanGenerationRequest(request_id=f"{dialog['id']}-{i}",draft=draft,generation=generation,
                            messages=plan_messages(history),reference_facts=latest_reference_facts(history),reference_date=dataset["reference_date"])
                        before=request.model_dump_json();old_history=tuple(history)
                        update=await run_button_plan_generation(request,generate=generate)
                        generation,outcome=update.generation,update.result
                        checks=dict(input_preserved=request.model_dump_json()==before,history_unchanged=tuple(history)==old_history)
                        row.update(agent_calls=0,generation_calls=outcome.model_calls,limit_reached=False)
                    checks.update(conditions=draft.conditions.model_dump(mode="json")==expected,
                        generation=(outcome.status if outcome else None)==case["generation"])
                    if "offer" in case: checks["offer"]=(generation.offer.status if generation.offer else None)==case["offer"]
                    if outcome and outcome.status=="generated":
                        preview=outcome.preview
                        checks.update(basis=preview.basis_draft==draft,source=preview.trigger.source==case["source"],
                            unknown_dates=draft.conditions.start_date is not None or all(s.starts_at is None and s.deadline is None
                                and all(a.due_date is None for a in s.actions) for s in preview.steps))
                    row.update(checks=checks,passed=all(checks.values()),draft=draft.model_dump(mode="json"),
                        generation=generation.model_dump(mode="json"),outcome=outcome.model_dump(mode="json") if outcome else None,
                        compositions=list(compositions),validation_reasons=list(validation_reasons),
                        provider_errors=list(provider_errors),schema_errors=list(schema_errors))
                except Exception as error:
                    row.update(error_type=type(error).__name__,passed=False)
                row.update(ms=round((time.perf_counter()-started)*1000),http_calls=http_calls-before_http)
                report["turns"].append(row);save()
                print(dialog["id"],i,"PASS" if row["passed"] else "MISMATCH",row["ms"],"ms",flush=True)
                if "error_type" in row:
                    row["remaining_dialog_turns_skipped"]=len(dialog["turns"])-i
                    break
    rows=report["turns"]
    report.update(state="COMPLETED",http_calls=http_calls,summary=dict(turns=len(rows),passed=sum(r["passed"] for r in rows),
        expected_turns=sum(len(x["turns"]) for x in dataset["dialogs"]),median_ms=statistics.median(r["ms"] for r in rows),
        max_ms=max(r["ms"] for r in rows),agent_calls=sum(r.get("agent_calls",0) for r in rows),generation_calls=sum(r.get("generation_calls",0) for r in rows)))
    save();print(json.dumps(report["summary"],ensure_ascii=False),flush=True)
    return 0 if all(r["passed"] for r in rows) and len(rows)==report["summary"]["expected_turns"] else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json",type=Path,required=True)
    parser.add_argument("--dialog")
    args=parser.parse_args()
    raise SystemExit(asyncio.run(run(args.json,dialog_id=args.dialog)))
