"""합성 조건 추출 사례를 실제 모델로 실행한다. be/에서 python -m으로 실행."""

import asyncio
import json
from pathlib import Path
import subprocess
import time
import sys
import hashlib

from app.ai.config import get_settings
from app.ai.errors import AIError
from app.ai.features.planning.legacy.nodes import PROMPT_VERSION, extract_condition_changes
from app.ai.features.planning.legacy.schemas import ConditionExtractionInput, PlanningConditions

CASES = Path(__file__).parents[1] / "tests/fixtures/eval/planning_conditions.json"


async def main() -> None:
    settings = get_settings()
    settings.require_api()
    fixture = json.loads(CASES.read_text(encoding="utf-8"))
    results = []
    for case in fixture["cases"]:
        request = ConditionExtractionInput.model_validate(case["request"])
        expected = PlanningConditions.model_validate(
            request.conditions.model_dump(mode="json") | case["expected_changes"]
        )
        started = time.perf_counter()
        try:
            result = await extract_condition_changes(request)
            wrong_fields = [field for field in PlanningConditions.model_fields
                            if getattr(result.candidate_conditions, field) != getattr(expected, field)]
            unresolved = {item.field for item in result.unresolved}
            results.append({
                "id": case["id"], "status": result.status,
                "match": not wrong_fields and result.status == case["expected_status"]
                and unresolved == set(case["expected_unresolved_fields"]),
                "wrong_fields": wrong_fields, "ms": result.extraction_ms,
                "candidate_conditions": result.candidate_conditions.model_dump(mode="json"),
                "applied_operations": [op.model_dump(mode="json") for op in result.applied_operations],
                "unresolved": [item.model_dump(mode="json") for item in result.unresolved],
                "validation_errors": result.validation_errors,
            })
        except AIError as error:
            results.append({"id": case["id"], "match": False, "error": type(error).__name__,
                            "ms": round((time.perf_counter() - started) * 1000)})
        print(f"{case['id']}: {'PASS' if results[-1]['match'] else 'FAIL'} ({results[-1]['ms']} ms)", file=sys.stderr, flush=True)
    print(json.dumps({
        "model": settings.model, "prompt_version": PROMPT_VERSION,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "review_status": fixture["review_status"], "count": len(results),
        "fixture_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "exact_matches": sum(row["match"] for row in results), "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
