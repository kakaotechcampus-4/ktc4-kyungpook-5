"""지금의 판단 경로와 Jev 경로를 같은 발화로 번갈아 불러, 발화부터 검색어를 받기까지의 시간을 견준다 (#245).

    지금   발화 → luna (판단 + 검색어) 한 번
    Jev    발화 → Jev (판단) → 확률이 임계값 이상이면 luna (검색어만, meeting-query-v1)

조회가 필요 없는 말은 Jev 한 번으로 끝나 빨라지고, 조회할 말은 호출이 두 번이라 느려질 수 있다.
다른 날 잰 값을 더하면 게이트웨이 지연이 날마다 달라 비교할 수 없으므로 같은 측정에서 번갈아 잰다.
뒤의 기록 검색은 두 경로가 같아 재지 않는다. 키가 필요해 CI에서 돌리지 않는다.

    cd be && uv run python app/ai/scripts/check_meeting_path.py [--threshold 0.35] [--repeat 3] \\
        [--limit 5] [--env-file .env] [--json 결과.json]

- 문항: 회의 판단 평가 세트(#115) 개발용 전체. 정답이 조회 필요·아님·둘 다 허용인 발화로 나눠 센다
- 두 경로를 발화마다 이어서 부르고, 발화와 회차마다 먼저 부르는 쪽을 바꾼다. 차례로 재면 뒤에 잰 쪽이 빨랐다(#111)
- Jev 경로는 실제로 바꿨을 때처럼 확률이 임계값 이상일 때만 검색어 호출을 붙인다. 경로 시간은 Jev 호출 시작부터
  검색어 호출이 끝날 때까지다
- luna 호출은 check_meeting_query.py와 같은 함수·설정(추론 끔, 제한 시간 10초)이고, Jev 호출은 check_jev_judge.py와 같다
- 노트북에서 인터넷을 거쳐 잰 값이다. 배포 서버에서 잰 값이 아니다
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles

from dotenv import dotenv_values, load_dotenv

from app.ai.config import get_settings
from app.ai.features.meeting.context import (
    MEETING_TIMEZONE,
    PROMPT_VERSION,
    QUERY_PROMPT_VERSION,
    build_judge_input,
)
from app.ai.features.meeting.nodes import JUDGE_TIMEOUT_SECONDS, get_judge_model
from app.ai.features.meeting.questions import QUESTIONS_VERSION, judge_questions
from app.ai.scripts.check_jev_judge import MODEL as JEV_MODEL
from app.ai.scripts.check_jev_judge import JevClient, _judge
from app.ai.scripts.check_meeting_judge import EVAL_SET, load_requests
from app.ai.scripts.check_meeting_query import _call

# 개발용에서 고른 Jev 임계값(meeting-evaluation.md 2026-11-03 개발용 측정)
THRESHOLD = 0.35
PATHS = ("luna", "jev")
# 정답으로 나눈 묶음. 둘 다 허용은 어느 쪽으로 판단해도 맞으므로 따로 센다
GROUPS = ("lookup", "no_lookup", "either")
# 세지 않는 준비 호출 수. 두 경로(검색어만 받는 호출 포함)를 이만큼씩 먼저 부른다
WARMUP = 2


def group_of(row: dict) -> str:
    if row.get("either"):
        return "either"
    return "lookup" if row["needs_lookup"] else "no_lookup"


async def luna_path(request) -> dict:
    """지금 경로. 판단과 검색어를 한 번에 받는다"""
    call = await _call("judge", request)
    if "error" in call:
        return {"error": call["error"], "ms": call["ms"]}
    return {"ms": call["ms"], "lookup": call["needs_lookup"], "luna_calls": 1}


async def jev_path(client: JevClient, request, questions: dict, threshold: float) -> dict:
    """Jev 경로. Jev가 조회로 본 발화에만 검색어만 받는 luna 호출을 붙인다"""
    started = time.perf_counter()
    # Jev 클라이언트는 동기 호출이라 스레드에서 부른다. 한 번에 하나씩 부르므로 순서는 그대로다
    decision = await asyncio.to_thread(_judge, client, build_judge_input(request), questions)
    if "error" in decision:
        return {"error": f"jev {decision['error']}", "ms": round((time.perf_counter() - started) * 1000)}
    record = {"jev_ms": round(decision["ms"]), "p_true": decision["p_true"], "lookup": decision["p_true"] >= threshold}
    if record["lookup"]:
        query = await _call("query", request)
        if "error" in query:
            return {**record, "error": f"query {query['error']}", "ms": round((time.perf_counter() - started) * 1000)}
        record["query_ms"] = query["ms"]
    record["ms"] = round((time.perf_counter() - started) * 1000)
    record["luna_calls"] = int(record["lookup"])
    return record


def latency(ms: list[float]) -> dict:
    ms = sorted(ms)
    return {
        "n": len(ms),
        "p50_s": round(median(ms) / 1000, 2) if ms else None,
        "p95_s": round(quantiles(ms, n=20)[18] / 1000, 2) if len(ms) >= 2 else None,
        "max_s": round(ms[-1] / 1000, 2) if ms else None,
        "mean_s": round(mean(ms) / 1000, 2) if ms else None,
    }


def summarize(records: list[dict]) -> dict:
    """경로별 지연을 묶음별로 낸다. 두 경로가 모두 성공한 쌍만 센다. 같은 발화·같은 순간끼리 견주기 위해서다"""
    pairs = [r for r in records if all("error" not in r[path] for path in PATHS)]
    out = {}
    for name in ("all", *GROUPS):
        chosen = pairs if name == "all" else [r for r in pairs if r["group"] == name]
        if not chosen:
            continue
        jev_with_query = [r["jev"] for r in chosen if r["jev"]["lookup"]]
        out[name] = {
            "pairs": len(chosen),
            "luna": latency([r["luna"]["ms"] for r in chosen]),
            "jev": latency([r["jev"]["ms"] for r in chosen]),
            # 같은 발화에서 Jev 경로가 더 빨랐던 수
            "jev_faster": sum(r["jev"]["ms"] < r["luna"]["ms"] for r in chosen),
            # Jev 경로를 둘로 나눈 값. 검색어 호출은 Jev가 조회로 본 발화에만 있다
            "jev_judge_only": latency([r["jev"]["jev_ms"] for r in chosen]),
            "jev_with_query": len(jev_with_query),
            "query_only": latency([j["query_ms"] for j in jev_with_query]),
            # luna를 부른 수. 지금은 발화마다 한 번, Jev 경로는 조회로 본 발화에만 한 번
            "luna_calls": {path: sum(r[path]["luna_calls"] for r in chosen) for path in PATHS},
        }
    return out


async def run(args, client: JevClient) -> dict:
    items = load_requests(EVAL_SET, splits=("dev",))[: args.limit]
    questions = judge_questions()
    # 준비 호출. 첫 호출은 연결을 맺느라 느리거나 제한 시간을 넘긴다(시험에서 10초). 회의 중에는 연결이 이어져 있으므로 세지 않는다
    for _ in range(WARMUP):
        await luna_path(items[0][1])
        await jev_path(client, items[0][1], questions, threshold=0.0)
    records = []
    for rep in range(args.repeat):
        print(f"── {rep + 1}/{args.repeat}회")
        for index, (row, request) in enumerate(items):
            order = PATHS if (rep + index) % 2 == 0 else PATHS[::-1]
            result = {}
            for path in order:
                if path == "luna":
                    result[path] = await luna_path(request)
                else:
                    result[path] = await jev_path(client, request, questions, args.threshold)
            records.append({"id": row["id"], "heard": row["heard"], "group": group_of(row), "rep": rep, "first": order[0], **result})
            shown = "  ".join(
                f"{p} {result[p].get('ms', '-'):>5}ms{' 조회' if result[p].get('lookup') else '     '}{' ' + result[p]['error'] if 'error' in result[p] else ''}"
                for p in PATHS
            )
            print(f"  {row['id']:6} {group_of(row):9} {shown}  {row['heard']}")

    return {
        "settings": {
            "luna_model": get_settings().model,
            "max_retries": get_judge_model().max_retries,
            "judge_prompt_version": PROMPT_VERSION,
            "query_prompt_version": QUERY_PROMPT_VERSION,
            "jev_model": client.model,
            "questions_version": QUESTIONS_VERSION,
            "threshold": args.threshold,
            "eval": EVAL_SET.name,
            "items": len(items),
            "repeat": args.repeat,
            "warmup": WARMUP,
            "timeout_s": JUDGE_TIMEOUT_SECONDS,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "summary": summarize(records),
        "errors": [{"id": r["id"], "rep": r["rep"], path: r[path]["error"]} for r in records for path in PATHS if "error" in r[path]],
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"Jev 확률이 이 값 이상이면 검색어 호출을 붙인다. 기본 {THRESHOLD}")
    parser.add_argument("--repeat", type=int, default=3, help="문항 전체를 도는 횟수")
    parser.add_argument("--limit", type=int, help="앞에서부터 이 수만큼만 잰다. 스크립트를 시험할 때 쓴다")
    parser.add_argument("--jev-model", default=JEV_MODEL, help=f"Jev 모델 ID. 기본 {JEV_MODEL}")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="AI_*·JEV_*를 읽을 파일")
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    args = parser.parse_args()

    # eval_retrieval은 불러올 때 be/.env를 덮어 읽으므로 --env-file보다 먼저 불러온다(check_meeting_judge.py와 같다)
    from app.ai.scripts.eval_retrieval import _git

    load_dotenv(args.env_file.resolve(), override=True)
    env = {**dotenv_values(args.env_file), **{k: v for k, v in os.environ.items() if k.startswith("JEV_")}}
    if not env.get("JEV_BASE_URL") or not env.get("JEV_API_KEY"):
        parser.error(f"JEV_BASE_URL·JEV_API_KEY가 {args.env_file}에 없다")
    client = JevClient(env["JEV_BASE_URL"], env["JEV_API_KEY"], args.jev_model, JUDGE_TIMEOUT_SECONDS)

    report = asyncio.run(run(args, client))
    report["settings"] = {**_git(), **report["settings"]}
    print("\n설정", json.dumps(report["settings"], ensure_ascii=False))
    for name, summary in report["summary"].items():
        print(f"\n[{name}] 쌍 {summary['pairs']}, Jev 경로가 더 빠름 {summary['jev_faster']}, luna 호출 {summary['luna_calls']}")
        for key in ("luna", "jev", "jev_judge_only", "query_only"):
            print(f"  {key:15}", json.dumps(summary[key], ensure_ascii=False))
    if report["errors"]:
        print("오류", json.dumps(report["errors"], ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
