"""#177: 고정 케이스로 실제 모델의 계획 수정 검토(review_plan_edit)를 재고 결과를 저장한다.

실행(api 컨테이너, 모델 설정이 있는 곳):
  python -m app.ai.scripts.run_plan_review_eval --out app/ai/docs/planning/evaluation-results/plan-review-2026-11
키·base URL·요청 헤더는 읽지도 기록하지도 않는다. 케이스 id, 지연, outcome, 항목만 남긴다.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from app.ai import PlanEditReviewRequest, review_plan_edit

CASES_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval" / "plan_review_cases.json"


def judge(expect: dict, result: dict | None) -> dict:
    """기대와 비교한다. outcome이 any인 케이스는 자동 판정하지 않고 수동 확인으로 남긴다."""
    if result is None:
        return {"outcome_match": False, "mentions_match": False, "kind_match": None}
    mentioned = {code for item in result["items"] for code in item["step_codes"]}
    outcome_ok = expect["outcome"] in ("any", result["outcome"])
    mentions_ok = set(expect["must_mention_codes"]) <= mentioned and not (
        set(expect["must_not_mention_codes"]) & mentioned)
    kind = expect.get("expected_kind")
    kind_ok = None if kind is None else any(i["kind"] == kind for i in result["items"])
    return {"outcome_match": outcome_ok, "mentions_match": mentions_ok, "kind_match": kind_ok}


async def run_case(case: dict) -> dict:
    request = PlanEditReviewRequest.model_validate(case["request"])
    started = time.perf_counter()
    result, error = None, None
    try:
        result = (await review_plan_edit(request)).model_dump(mode="json")
    except Exception as exc:  # 오류 종류만 남기고 메시지는 남기지 않는다.
        error = type(exc).__name__
    latency_ms = round((time.perf_counter() - started) * 1000)
    checks = judge(case["expect"], result)
    passed = error is None and all(v is not False for v in checks.values())
    return {"id": case["id"], "expect": case["expect"], "latency_ms": latency_ms, "error": error,
            "result": result, "checks": checks, "passed": passed}


def summary_table(rows: list[dict]) -> str:
    lines = ["| id | 기대 | 실제 | 언급 코드 | 지연(ms) | 판정 |", "|---|---|---|---|---|---|"]
    for r in rows:
        res = r["result"]
        codes = sorted({c for i in res["items"] for c in i["step_codes"]}) if res else []
        actual = res["outcome"] if res else f"오류({r['error']})"
        lines.append(f"| {r['id']} | {r['expect']['outcome']} | {actual} | {', '.join(codes) or '-'} "
                     f"| {r['latency_ms']} | {'통과' if r['passed'] else '불일치'} |")
    return "\n".join(lines)


async def main(out: Path, label: str) -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    rows = [await run_case(case) for case in cases]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"results-{label}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table = summary_table(rows)
    (out / f"summary-{label}.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    print(f"{sum(r['passed'] for r in rows)}/{len(rows)} passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()
    asyncio.run(main(args.out, args.label))
