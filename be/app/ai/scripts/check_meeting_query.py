"""검색어만 받는 호출과 지금의 판단 + 검색어 호출을 같은 발화로 번갈아 불러 지연과 검색어를 견준다 (#117).

판단을 Laya로 바꾸면 조회로 본 발화에는 검색어만 받는 LLM 호출이 남는다.
바꾸는 기준은 "Laya 판단 + 검색어만 받는 호출"의 p95가 지금 판단의 p95 이하인 것이다(architecture.md 1단계).
키가 필요해 CI에서 돌리지 않는다.

    cd be && uv run python app/ai/scripts/check_meeting_query.py [--repeat 3] [--env-file .env] [--json 결과.json]

- 문항: 회의 판단 평가 세트(#115) 개발용에서 조회 필요인 발화(둘 다 허용 제외). Laya가 맞게 조회로 본 경우만 이 호출을 부른다
- 두 호출을 발화마다 번갈아 부르고 회차마다 먼저 부르는 쪽을 바꾼다. 차례로 재면 뒤에 잰 쪽이 빨랐다(#111)
- 두 호출 모두 같은 모델·설정(추론 끔)이고 제한 시간 10초다. 넘기면 오류로 센다
- 검색어는 첫 회차 값을 견준다. 같은지와 다른 검색어 목록을 낸다. 기록을 찾아 맞는지는 재지 않는다
- Laya 판단 지연은 이 스크립트가 재지 않는다. check_laya_judge.py로 따로 잰다
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles

from dotenv import load_dotenv
from langchain_core.callbacks import get_usage_metadata_callback

from app.ai.config import get_settings
from app.ai.features.meeting.context import (
    MEETING_TIMEZONE,
    PROMPT_VERSION,
    QUERY_PROMPT_VERSION,
    build_judge_messages,
    build_query_messages,
)
from app.ai.features.meeting.nodes import JUDGE_TIMEOUT_SECONDS, call_judge_model, call_query_model, get_judge_model
from app.ai.scripts.check_meeting_judge import EVAL_SET, _cost_per_1000, load_requests

VARIANTS = ("judge", "query")


async def _call(variant: str, request) -> dict:
    """호출 하나. 재시도가 있었다면 모든 호출의 토큰을 더한다. 실제로 내는 값이기 때문이다"""
    started = time.perf_counter()
    with get_usage_metadata_callback() as usage:
        try:
            async with asyncio.timeout(JUDGE_TIMEOUT_SECONDS):
                if variant == "judge":
                    output = await call_judge_model(build_judge_messages(request))
                else:
                    output = await call_query_model(build_query_messages(request))
        except Exception as error:  # 측정에서는 실패도 한 건으로 센다
            return {"error": f"{type(error).__name__}: {error}", "ms": round((time.perf_counter() - started) * 1000)}
    ms = round((time.perf_counter() - started) * 1000)
    tokens = {"input": 0, "cached": 0, "output": 0}
    for item in usage.usage_metadata.values():
        tokens["input"] += item.get("input_tokens", 0)
        tokens["cached"] += item.get("input_token_details", {}).get("cache_read", 0) or 0
        tokens["output"] += item.get("output_tokens", 0)
    record = {"ms": ms, "query": output.query.strip(), "tokens": tokens}
    if variant == "judge":
        record["needs_lookup"] = output.needs_lookup
    return record


def _summary(records: list[dict], model: str) -> dict:
    done = [r for r in records if "error" not in r]
    ms = sorted(r["ms"] for r in done)
    tokens = {key: round(mean(r["tokens"][key] for r in done), 1) if done else None for key in ("input", "cached", "output")}
    return {
        "calls": len(records),
        "errors": len(records) - len(done),
        "p50_s": round(median(ms) / 1000, 2) if ms else None,
        "p95_s": round(quantiles(ms, n=20)[18] / 1000, 2) if len(ms) >= 2 else None,
        "max_s": round(ms[-1] / 1000, 2) if ms else None,
        "faster": None,
        "tokens_per_call": tokens,
        "krw_per_1000": _cost_per_1000(model, tokens) if done else None,
    }


async def run(repeat: int) -> dict:
    items = [
        (row, request)
        for row, request in load_requests(EVAL_SET, splits=("dev",))
        if row["needs_lookup"] and not row.get("either")
    ]
    records = []
    for rep in range(repeat):
        for index, (row, request) in enumerate(items):
            order = VARIANTS if (rep + index) % 2 == 0 else VARIANTS[::-1]
            pair = {variant: await _call(variant, request) for variant in order}
            records.append({"id": row["id"], "heard": row["heard"], "rep": rep, "first": order[0], **pair})
            shown = "  ".join(
                f"{v} {pair[v].get('ms', '-'):>5}ms {pair[v].get('query') or pair[v].get('error', '')}" for v in VARIANTS
            )
            print(f"  {rep} {row['id']:6} {shown}")

    model = get_settings().model
    summary = {variant: _summary([r[variant] for r in records], model) for variant in VARIANTS}
    both = [r for r in records if "error" not in r["judge"] and "error" not in r["query"]]
    for variant, other in (VARIANTS, VARIANTS[::-1]):
        summary[variant]["faster"] = f"{sum(r[variant]['ms'] < r[other]['ms'] for r in both)} / {len(both)}"

    first = [r for r in both if r["rep"] == 0]
    changed = [
        {"id": r["id"], "heard": r["heard"], "judge": r["judge"]["query"], "query": r["query"]["query"]}
        for r in first
        if r["judge"]["query"] != r["query"]["query"]
    ]
    return {
        "settings": {
            "model": model,
            "max_retries": get_judge_model().max_retries,
            "judge_prompt_version": PROMPT_VERSION,
            "query_prompt_version": QUERY_PROMPT_VERSION,
            "eval": EVAL_SET.name,
            "items": len(items),
            "repeat": repeat,
            "timeout_s": JUDGE_TIMEOUT_SECONDS,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "summary": summary,
        "queries": {
            "compared": len(first),
            "same": len(first) - len(changed),
            # 판단 호출이 조회 아님으로 본 발화. 검색어만 받는 호출은 조회 여부를 묻지 않는다
            "judge_said_no_lookup": sum(not r["judge"]["needs_lookup"] for r in first),
            "changed": changed,
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3, help="문항 전체를 도는 횟수")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="AI_* 를 읽을 파일")
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    args = parser.parse_args()

    # eval_retrieval은 불러올 때 be/.env를 덮어 읽으므로 --env-file보다 먼저 불러온다(check_meeting_judge.py와 같다)
    from app.ai.scripts.eval_retrieval import _git

    load_dotenv(args.env_file.resolve(), override=True)
    report = asyncio.run(run(args.repeat))
    report["settings"] = {**_git(), **report["settings"]}

    print("\n설정", json.dumps(report["settings"], ensure_ascii=False))
    for variant, summary in report["summary"].items():
        print(f"  {variant}", json.dumps(summary, ensure_ascii=False))
    queries = report["queries"]
    print(f"검색어 같음 {queries['same']} / {queries['compared']}, 판단 호출이 조회 아님으로 본 발화 {queries['judge_said_no_lookup']}")
    for item in queries["changed"]:
        print(f"  {item['id']}: 판단 {item['judge']!r} / 검색어만 {item['query']!r}   ({item['heard']})")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if any(s["errors"] for s in report["summary"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
