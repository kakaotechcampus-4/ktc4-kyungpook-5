"""실제 회의 판단 기록을 Jev로 다시 판단해 그때 luna의 판단과 견준다 (#245).

운영 BE는 회의 판단마다 luna에 넘긴 요청을 context_decisions.judge_input에 그대로 저장한다(#241).
그 요청으로 같은 입력 글(build_judge_input)을 다시 만들어 Jev에 보내므로, luna가 본 글과 같은 글로 판단한다.
Jev는 서버에 올리지 않아도 된다. 키가 필요해 CI에서 돌리지 않는다.

    cd be && uv run python app/ai/scripts/rejudge_meeting_decisions.py --decisions 판단기록.jsonl \\
        [--threshold 0.35] [--repeat 1] [--json 결과.json]

- 입력: 운영 DB에서 내보낸 판단 기록 JSONL. 한 줄에 판단 하나이고 id·meeting_id·status·route·question·
  policy_version·model_version·judge_ms·created_at·judge_input 칸을 쓴다. 내보내는 명령은 #245 코멘트에 있다
- judge_input이 없는 기록(#241 전 기록, Discord 판단)은 다시 만들 수 없어 건너뛰고 수만 센다
- 정답은 없다. luna와 Jev가 같게 봤는지(일치)와, 갈린 발화 목록을 낸다. 갈린 발화는 사람이 정답을 붙일 후보다
  (architecture.md "실제 회의에서 검수할 발화"). luna 판단이 실패한 기록(route ERROR)은 일치에서 빼고 따로 센다
- 임계값은 평가 세트 개발용에서 고른 0.35가 기본이다
- luna 판단 시간은 운영 서버에서 잰 judge_ms이고, Jev 지연은 이 스크립트를 돌린 곳에서 잰 값이다
- **결과에는 실제 회의 발화가 들어 있다.** 레포와 이슈에 올리지 않고, 이슈에는 수만 적는다
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median, quantiles

from dotenv import dotenv_values

from app.ai.features.meeting.context import MEETING_TIMEZONE, build_judge_input
from app.ai.features.meeting.questions import QUESTIONS_VERSION, judge_questions
from app.ai.features.meeting.schemas import JudgeUtteranceRequest
from app.ai.scripts.check_jev_judge import MODEL, TIMEOUT_SECONDS, JevClient, _judge

THRESHOLD = 0.35
# 판단 경로가 정해진 luna 판단. ERROR는 luna가 판단하지 못한 기록이다
LUNA_DECIDED = ("RAG", "NONE")


def load_decisions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def jev_inputs(decisions: list[dict]) -> tuple[list[tuple[dict, str]], list[dict]]:
    """판단 기록마다 Jev에 보낼 입력 글. judge_input이 없거나 읽을 수 없는 기록은 이유와 함께 따로 돌려준다"""
    items, skipped = [], []
    for decision in decisions:
        if not decision.get("judge_input"):
            skipped.append({"id": decision.get("id"), "reason": "judge_input 없음"})
            continue
        try:
            request = JudgeUtteranceRequest.model_validate(decision["judge_input"])
        except ValueError as error:
            skipped.append({"id": decision.get("id"), "reason": f"읽을 수 없음: {type(error).__name__}"})
            continue
        items.append((decision, build_judge_input(request)))
    return items, skipped


def compare(records: list[dict]) -> dict:
    """luna 판단(RAG·NONE)과 Jev 판단(조회·아님)을 2×2로 센다. luna가 판단하지 못한 기록은 뺀다"""
    decided = [r for r in records if r["luna_route"] in LUNA_DECIDED]
    table = Counter((r["luna_route"] == "RAG", r["jev_lookup"]) for r in decided)
    agree = table[(True, True)] + table[(False, False)]
    return {
        "compared": len(decided),
        "agree": f"{agree} / {len(decided)}",
        "luna_rag_jev_lookup": table[(True, True)],
        "luna_rag_jev_no": table[(True, False)],
        "luna_none_jev_lookup": table[(False, True)],
        "luna_none_jev_no": table[(False, False)],
        "luna_error": sum(r["luna_route"] not in LUNA_DECIDED for r in records),
    }


def _percentiles_ms(values: list[float]) -> dict:
    values = sorted(values)
    return {
        "n": len(values),
        "p50_ms": round(median(values), 1) if values else None,
        "p95_ms": round(quantiles(values, n=20)[18], 1) if len(values) >= 2 else None,
    }


def run(args, client: JevClient, git: dict) -> dict:
    decisions = load_decisions(args.decisions)
    items, skipped = jev_inputs(decisions)
    questions = judge_questions()

    passes = []
    for n in range(args.repeat):
        print(f"── {n + 1}/{args.repeat}회 ({len(items)}건)")
        passes.append([_judge(client, state, questions) for _, state in items])

    records, errors = [], []
    for i, ((decision, _), outcome) in enumerate(zip(items, passes[0])):
        if "error" in outcome:
            errors.append({"id": decision["id"], "error": outcome["error"]})
            continue
        lookup = outcome["p_true"] >= args.threshold
        record = {
            "id": decision["id"],
            "meeting_id": decision.get("meeting_id"),
            "created_at": decision.get("created_at"),
            "status": decision.get("status"),
            "text": decision["judge_input"]["utterance"]["text"],
            "luna_route": decision.get("route"),
            "luna_query": decision.get("question"),
            "luna_policy": decision.get("policy_version"),
            "p_true": outcome["p_true"],
            **({"p_passes": [o[i].get("p_true") for o in passes]} if len(passes) > 1 else {}),
            "jev_lookup": lookup,
        }
        records.append(record)
        if decision.get("route") in LUNA_DECIDED and (decision["route"] == "RAG") != lookup:
            print(f"  갈림 {decision['id']}  luna {decision['route']:4}  Jev P={outcome['p_true']:.2f}  {record['text']}")

    done = [o for outcomes in passes for o in outcomes if "error" not in o]
    luna_ms = [d["judge_ms"] for d, _ in items if d.get("judge_ms") is not None]
    return {
        "settings": {
            **git,
            "decisions": args.decisions.name,
            "model": client.model,
            "served_models": sorted({o["served_model"] for o in done if o.get("served_model")}),
            "questions_version": QUESTIONS_VERSION,
            "threshold": args.threshold,
            "repeat": args.repeat,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "input": {
            "decisions": len(decisions),
            "rejudged": len(items),
            "skipped": len(skipped),
            "meetings": len({d.get("meeting_id") for d, _ in items}),
            "luna_policy_versions": dict(Counter(d.get("policy_version") for d, _ in items)),
            "status": dict(Counter(d.get("status") for d, _ in items)),
            "created_at": [min((d.get("created_at") or "") for d, _ in items), max((d.get("created_at") or "") for d, _ in items)]
            if items else None,
        },
        "comparison": compare(records),
        # 정한 임계값에서 회차에 따라 조회·아님이 뒤집힌 판단. --repeat 2 이상에서만 센다
        "jev_flips": [
            r["id"] for r in records
            if "p_passes" in r and len({p >= args.threshold for p in r["p_passes"] if p is not None}) > 1
        ],
        "latency": {"luna_judge_ms_production": _percentiles_ms(luna_ms), "jev": _percentiles_ms([o["ms"] for o in done])},
        "errors": errors,
        "skipped": skipped,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=Path, required=True, help="운영 DB에서 내보낸 판단 기록 JSONL")
    parser.add_argument("--model", default=MODEL, help=f"Jev 모델 ID. 기본 {MODEL}")
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"P(true)가 이 값 이상이면 조회로 본다. 기본 {THRESHOLD}")
    parser.add_argument("--repeat", type=int, default=1, help="같은 판단을 다시 보내는 횟수. 판단은 첫 회로 한다")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS, help=f"호출 하나의 제한 시간(초). 기본 {TIMEOUT_SECONDS}")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="JEV_BASE_URL·JEV_API_KEY를 읽을 파일")
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일. 실제 발화가 들어 있으니 레포에 두지 않는다")
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("임계값은 0과 1 사이다")

    env = {**dotenv_values(args.env_file), **{k: v for k, v in os.environ.items() if k.startswith("JEV_")}}
    if not env.get("JEV_BASE_URL") or not env.get("JEV_API_KEY"):
        parser.error(f"JEV_BASE_URL·JEV_API_KEY가 {args.env_file}에 없다")
    client = JevClient(env["JEV_BASE_URL"], env["JEV_API_KEY"], args.model, args.timeout)

    # eval_retrieval은 불러올 때 be/.env를 덮어 읽는다. 테스트가 이 파일을 불러와도 환경을 바꾸지 않게 여기서 불러온다
    from app.ai.scripts.eval_retrieval import _git

    report = run(args, client, _git())
    print("\n설정", json.dumps({k: report["settings"][k] for k in ("model", "served_models", "questions_version", "threshold")}, ensure_ascii=False))
    print("입력", json.dumps(report["input"], ensure_ascii=False))
    print("비교", json.dumps(report["comparison"], ensure_ascii=False))
    print("지연", json.dumps(report["latency"], ensure_ascii=False))
    if report["jev_flips"]:
        print("회차에 따라 뒤집힘", report["jev_flips"])
    for name in ("errors", "skipped"):
        if report[name]:
            print(name, json.dumps(report[name], ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
