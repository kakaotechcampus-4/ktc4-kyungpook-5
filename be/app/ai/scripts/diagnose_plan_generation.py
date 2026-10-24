"""생성 실패를 고정 입력으로 재현한다. 응답 원문 대신 종료 상태·토큰·오류 유형만 기록한다."""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.ai.config import AISettings
from app.ai.contracts import ChatTurn
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.generation.graph import PROMPT, PROMPT_VERSION, run_plan_generation, validate_plan
from app.ai.features.planning.generation.model import PLAN_MAX_OUTPUT_TOKENS
from app.ai.features.planning.generation.schemas import ChatGenerationTrigger, PlanGenerationInput
from app.ai.features.planning.schemas import PlanningConditions
from app.ai.llm import ainvoke_structured, build_chat_model


AI_DIR = Path(__file__).resolve().parents[1]
CASES = AI_DIR / "tests/fixtures/eval/planning_generation_limits.json"


def response_summary(response: httpx.Response) -> dict:
    """진단용으로 읽은 응답에서 허용 필드만 반환한다. 원문·헤더·URL은 저장하지 않는다."""
    try:
        data = response.json()
    except ValueError:
        data = None
        for line in response.text.splitlines():
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                except ValueError:
                    continue
                if event.get("type") in ("response.completed", "response.incomplete"):
                    data = event["response"]
        if data is None:
            return dict(http_status=response.status_code, terminal_response=False)
    content = "".join(c.get("text", "") for o in data.get("output", [])
        for c in o.get("content", []) if c.get("type") == "output_text")
    usage = data.get("usage") or {}
    row = dict(http_status=response.status_code, status=data.get("status"),
        incomplete_reason=(data.get("incomplete_details") or {}).get("reason"), text_chars=len(content),
        output_tokens=usage.get("output_tokens"),
        reasoning_tokens=(usage.get("output_tokens_details") or {}).get("reasoning_tokens"))
    if content:
        try:
            json.loads(content)
            row["valid_json"] = True
        except json.JSONDecodeError as error:
            row.update(valid_json=False, json_error=error.msg, json_error_pos=error.pos)
    return row


async def run(output: Path, *, streaming: bool, max_output_tokens: int | None) -> int:
    if output.exists():
        raise ValueError("이전 결과를 덮어쓰지 않도록 새 출력 경로를 지정하세요")
    settings = AISettings()
    settings.require_api()
    dataset = json.loads(CASES.read_text())
    paths = [Path(__file__), CASES, AI_DIR / "llm.py", AI_DIR / "features/planning/generation/graph.py",
             AI_DIR / "features/planning/generation/model.py"]
    report = dict(state="RUNNING", started_at=datetime.now(timezone.utc).isoformat(), model=settings.model,
        prompt=PROMPT_VERSION, prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        code_sha256={str(p.relative_to(AI_DIR)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        max_output_tokens=max_output_tokens, streaming=streaming, reasoning="provider default", cases=[])
    rows = []
    async def observe(response):
        # 진단 때만 스트림 전체를 버퍼링해 최종 응답을 분석한다. 지연 성능 비교용이 아니다.
        await response.aread()
        rows.append(response_summary(response))
    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    save()
    async with httpx.AsyncClient(event_hooks={"response": [observe]}) as client:
        kwargs = {"max_tokens": max_output_tokens} if max_output_tokens is not None else {}
        model = build_chat_model(settings, streaming=streaming, http_async_client=client, **kwargs)
        for case in dataset["cases"]:
            rows.clear()
            errors, captured = [], []
            request = PlanGenerationInput(basis_draft=PlanningDraft(conditions=PlanningConditions(**case["conditions"])),
                trigger=ChatGenerationTrigger(request_id=case["id"], quote="그렇게하자"),
                reference_date=dataset["reference_date"], messages=(
                    ChatTurn(role="ASSISTANT", content="현재 조건으로 계획 초안을 만들어볼까요?"),
                    ChatTurn(role="USER", content="그렇게하자")))
            async def invoke(messages, schema):
                try:
                    answer = await ainvoke_structured(messages, schema, model=model)
                    captured.append(answer)
                    return answer
                except Exception as error:
                    cause = error
                    for _ in range(6):
                        if cause is None:
                            break
                        entry = dict(type=type(cause).__name__)
                        if isinstance(cause, ValidationError):
                            entry["fields"] = [dict(type=e["type"], loc=e["loc"]) for e in
                                cause.errors(include_input=False, include_context=False, include_url=False)]
                        errors.append(entry)
                        cause = cause.__cause__
                    raise
            started = time.perf_counter()
            row = dict(id=case["id"], conditions=case["conditions"])
            try:
                result = await run_plan_generation(request, invoke=invoke)
                validation_reason = None
                if result.status == "failed" and captured:
                    try:
                        validate_plan(dict(request=request, composition=captured[-1]))
                    except Exception as error:
                        validation_reason = type(error).__name__
                row.update(status=result.status, model_calls=result.model_calls, validation_reason=validation_reason)
            except Exception as error:
                # 400 같은 비재시도 예외도 본문 없이 남기고 같은 잘못된 설정으로 반복하지 않는다.
                row.update(status="error", error_type=type(error).__name__)
            row.update(ms=round((time.perf_counter() - started) * 1000), errors=errors, http=list(rows))
            report["cases"].append(row)
            save()
            print(case["id"], row["status"], flush=True)
            if row["status"] == "error":
                break
    report.update(state="COMPLETED", expected_cases=len(dataset["cases"]))
    save()
    return 0 if len(report["cases"]) == len(dataset["cases"]) and all(
        row["status"] == "generated" for row in report["cases"]) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--transport", choices=("streaming", "regular"), default="streaming")
    parser.add_argument("--max-output-tokens", type=int, default=PLAN_MAX_OUTPUT_TOKENS,
                        help="0이면 모델 기본값을 사용합니다. 보통은 8192입니다")
    args = parser.parse_args()
    if args.max_output_tokens < 0:
        parser.error("출력 한도는 0 이상이어야 합니다")
    raise SystemExit(asyncio.run(run(args.json, streaming=args.transport == "streaming",
                                    max_output_tokens=args.max_output_tokens or None)))
