"""판단 전용 API Jev로 회의 판단 평가 문항을 판단한다 (#245).

Jev는 학습하지 않고 바로 쓰는 판단 모델이다. 요청 형식이 Laya와 같아서(state + questions, noul 확률)
luna·Laya와 같은 문항을 같은 입력 글과 같은 판단 질문으로 잰다. 키가 필요해 CI에서 돌리지 않는다.

    cd be && uv run python app/ai/scripts/check_jev_judge.py [--eval-set [--holdout | --split holdout2]] \\
        [--threshold 0.5] [--sweep 0.1 0.2 ...] [--luna luna결과.json] [--repeat 3] [--limit 5] [--json 결과.json]

- 입력 글은 build_judge_input, 질문은 questions.py의 record_lookup이다. Laya 측정(check_laya_judge.py)과 같다.
  질문 문구를 바꾸면 이전 측정과 비교할 수 없으므로 QUESTIONS_VERSION을 올린다
- 문구 후보는 코드를 바꾸지 않고 --questions <파일>로 잰다. 파일은 {"version": "...", "questions": {"record_lookup": {...}}}이고,
  결과의 questions_version에 파일의 version이 남는다
- 응답의 noul(조회가 필요할 확률)이 임계값(--threshold) 이상이면 조회로 본다. Jev는 확률을 소수 둘째 자리까지 준다
- 임계값 표(--sweep, 기본 0.01~0.99를 0.01 간격)는 개발용으로만 만든다. 임계값은 개발용에서 고르고
  홀드아웃은 고른 값을 확인하는 데만 쓴다
- --luna에 같은 문항을 잰 luna 결과(check_meeting_judge.py --json)를 주면 luna가 잡은 조회 중 놓친 것을 센다
- 모델은 버전을 고정해 부른다(기본 typesafe/jev-1.14). jev-latest는 새 버전이 나오면 같은 입력에도 답이 바뀐다.
  응답의 실제 모델 이름(예: typesafe/jev-1.14-20261014)을 결과에 남긴다
- 문항 전체를 --repeat번 판단한다. 판단 값은 첫 회를 쓰고(회의 중에도 한 번 부른다), 회차마다 같은 입력에
  같은 확률이 나왔는지와 정한 임계값에서 조회·아님이 뒤집힌 문항을 낸다. Jev는 같은 입력에도 확률이 조금씩 다르다.
  지연은 모든 회차의 호출 시간이고, 노트북에서 인터넷을 거쳐 잰 값이다
- 발화를 하나씩 차례로 부른다. 회의 중처럼 호출 하나의 지연을 보려는 것이다
- JEV_BASE_URL·JEV_API_KEY는 서버와 같은 설정(config.JevSettings)으로 --env-file(기본 be/.env)에서 읽고, 키는 출력하지 않는다.
  프로세스 환경변수가 있으면 그것을 먼저 쓴다
- 모델과 기본 임계값은 서버의 회의 판단과 같은 값(context.JEV_MODEL, JEV_THRESHOLD)이다
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean, median, quantiles

import httpx

from app.ai.config import JevSettings, jev_decisions_url
from app.ai.errors import AIConfigError
from app.ai.features.meeting.context import (
    JEV_MODEL,
    JEV_THRESHOLD,
    MEETING_TIMEZONE,
    build_judge_input,
)
from app.ai.features.meeting.questions import (
    EXTERNAL_WEB_SEARCH,
    QUESTIONS_VERSION,
    RECORD_LOOKUP,
    judge_questions,
)
from app.ai.scripts.check_meeting_judge import (
    add_eval_args,
    breakdown,
    eval_items,
    eval_record,
    luna_caught,
    luna_missed,
    summarize_probabilities,
    threshold_sweep,
)

MODEL = JEV_MODEL
THRESHOLD = JEV_THRESHOLD
# 확률이 0.01 단위로 오므로 임계값도 0.01 간격으로 본다
SWEEP = tuple(round(0.01 * i, 2) for i in range(1, 100))
# 회의 판단의 제한 시간(features/meeting/nodes.py JUDGE_TIMEOUT_SECONDS)과 같다
TIMEOUT_SECONDS = 10.0
# 입력 100만 토큰당 달러(ML API 모델 페이지, 2026-11-03). 출력은 과금되지 않는다
PRICE_USD_PER_M_INPUT = 0.042


class JevClient:
    """POST /v1/decisions 한 번에 판단 하나. OpenAI SDK에는 이 메서드가 없어 HTTP로 직접 부른다"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float):
        self.url = jev_decisions_url(base_url)
        self.model = model
        self.http = httpx.Client(headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)

    def decide(self, state: str, questions: dict) -> dict:
        started = time.perf_counter()
        response = self.http.post(self.url, json={"model": self.model, "state": state, "questions": questions})
        ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        body = response.json()
        return {
            "p_true": body["answers"][RECORD_LOOKUP]["noul"],
            "p_web": body["answers"].get(EXTERNAL_WEB_SEARCH, {}).get("noul", 0.0),
            "ms": ms,
            "prompt_tokens": body.get("usage", {}).get("prompt_tokens"),
            "served_model": body.get("model"),
        }


def _judge(client: JevClient, state: str, questions: dict) -> dict:
    try:
        return client.decide(state, questions)
    except (httpx.HTTPError, KeyError, ValueError) as error:
        # 키가 섞일 수 있는 요청 내용은 남기지 않고 오류 종류와 상태 코드만 남긴다
        status = getattr(getattr(error, "response", None), "status_code", None)
        return {"error": f"{type(error).__name__}" + (f" {status}" if status else "")}


def run(args, client: JevClient, git: dict) -> dict:
    path, key, groups, requests = eval_items(args)
    items = [(row, build_judge_input(request)) for row, request in requests][: args.limit]
    questions = args.questions_body or judge_questions()

    passes = []
    for n in range(args.repeat):
        print(f"── {n + 1}/{args.repeat}회")
        outcomes = []
        for row, state in items:
            outcome = _judge(client, state, questions)
            outcomes.append(outcome)
            if n == 0:
                mark = "!" if "error" in outcome else ("O" if (outcome["p_true"] >= args.threshold) == row["needs_lookup"] else "X")
                shown = outcome.get("error") or f"P={outcome['p_true']:.2f} {outcome['ms']:5.0f}ms"
                print(f"  {mark} {row['id']:6} {shown}  {row['heard']}")
        passes.append(outcomes)

    records, errors = [], []
    for i, ((row, _), outcome) in enumerate(zip(items, passes[0])):
        if "error" in outcome:
            errors.append({"id": row["id"], "error": outcome["error"]})
            continue
        # 판단은 첫 회로 한다. 회의 중에도 한 번만 부르기 때문이다. 회차별 확률은 흔들림을 보려고 남긴다
        p_passes = [outcomes[i].get("p_true") for outcomes in passes]
        records.append({
            **eval_record(row),
            "p_true": outcome["p_true"],
            "p_web": outcome.get("p_web", 0.0),
            **({"p_passes": p_passes} if len(passes) > 1 else {}),
            "pred": outcome["p_true"] >= args.threshold,
        })

    caught = luna_caught(args.luna) if args.luna else None
    # 임계값 표는 개발용으로만 만든다. 홀드아웃(holdout·holdout2)은 고른 값을 확인하는 데만 쓴다
    sweep_records = [r for r in records if r.get("split", "dev") == "dev"]
    # --split holdout2처럼 개발용이 없으면 표를 만들지 않는다
    sweep = threshold_sweep(sweep_records, args.sweep) if sweep_records else []
    if caught is not None:
        for row in sweep:
            row["luna_caught_missed"] = luna_missed(sweep_records, caught, row["threshold"])["missed"]

    done = [o for outcomes in passes for o in outcomes if "error" not in o]
    ms = sorted(o["ms"] for o in done)
    tokens = [o["prompt_tokens"] for o in done if o["prompt_tokens"] is not None]
    diffs = [
        abs(a["p_true"] - b["p_true"])
        for later in passes[1:]
        for a, b in zip(passes[0], later)
        if "error" not in a and "error" not in b
    ]
    return {
        "settings": {
            **git,
            "model": client.model,
            "served_models": sorted({o["served_model"] for o in done if o.get("served_model")}),
            "questions_version": args.questions_version or QUESTIONS_VERSION,
            "threshold": args.threshold,
            "luna": str(args.luna) if args.luna else None,
            "eval": path.name,
            key: groups,
            "limit": args.limit,
            "repeat": args.repeat,
            "timeout_s": args.timeout,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "summary": {**summarize_probabilities(records), "errors": len(errors)},
        f"by_{key}": {name: summarize_probabilities([r for r in records if r[key] == name]) for name in groups},
        **({"luna_caught_missed": {name: luna_missed([r for r in records if r[key] == name], caught) for name in groups}}
           if caught is not None else {}),
        **({"breakdown": {name: breakdown([r for r in records if r["split"] == name]) for name in groups}}
           if key == "split" else {}),
        # 임계값은 홀드아웃을 보지 않고 고른다. 홀드아웃은 고른 값을 확인하는 데만 쓴다
        "threshold_sweep": sweep,
        "latency": {
            "calls": len(ms),
            "errors": sum("error" in o for outcomes in passes for o in outcomes),
            "p50_ms": round(median(ms), 1) if ms else None,
            "p95_ms": round(quantiles(ms, n=20)[18], 1) if len(ms) >= 2 else None,
            "max_ms": round(ms[-1], 1) if ms else None,
            # 회차마다 같은 입력에 같은 확률이 나왔는지. 0이면 판단 값은 한 번 재면 된다
            "max_p_diff_between_passes": round(max(diffs), 4) if diffs else None,
            "items_changed_between_passes": sum(
                len({p for p in r["p_passes"] if p is not None}) > 1 for r in records if "p_passes" in r
            ),
            # 정한 임계값에서 회차에 따라 조회·아님이 뒤집힌 문항. 같은 말에 카드가 떴다 안 떴다 하는 수다
            "pred_flips_at_threshold": [
                r["id"] for r in records
                if "p_passes" in r and len({p >= args.threshold for p in r["p_passes"] if p is not None}) > 1
            ],
        },
        "cost": {
            "prompt_tokens_per_call": round(mean(tokens), 1) if tokens else None,
            "usd_per_1000": round(mean(tokens) * PRICE_USD_PER_M_INPUT / 1000, 4) if tokens else None,
        },
        "errors": errors,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=MODEL, help=f"Jev 모델 ID. 버전을 고정한다. 기본 {MODEL}")
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"P(true)가 이 값 이상이면 조회로 본다. 기본 {THRESHOLD}")
    parser.add_argument("--sweep", type=float, nargs="+", default=SWEEP, help="임계값 표의 후보. 기본 0.01~0.99, 0.01 간격")
    parser.add_argument("--repeat", type=int, default=3, help="문항 전체를 판단하는 횟수")
    parser.add_argument("--limit", type=int, help="앞에서부터 이 수만큼만 잰다. 스크립트를 시험할 때 쓴다")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS, help=f"호출 하나의 제한 시간(초). 기본 {TIMEOUT_SECONDS}")
    add_eval_args(parser)
    parser.add_argument("--luna", type=Path, help="같은 문항을 잰 luna 결과. luna가 잡은 조회 중 놓친 것을 센다")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="JEV_BASE_URL·JEV_API_KEY를 읽을 파일")
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    parser.add_argument("--questions", type=Path, help="질문 문구 후보 파일. 없으면 questions.py의 지금 문구")
    args = parser.parse_args()
    args.questions_body = args.questions_version = None
    if args.questions:
        candidate = json.loads(args.questions.read_text(encoding="utf-8"))
        if set(candidate.get("questions", {})) not in ({RECORD_LOOKUP}, {RECORD_LOOKUP, EXTERNAL_WEB_SEARCH}) or not candidate.get("version"):
            parser.error("--questions 파일에는 version과 record_lookup, 선택적 external_web_search 질문을 둔다")
        args.questions_body, args.questions_version = candidate["questions"], candidate["version"]
    if args.eval_set and args.set:
        parser.error("--eval-set에는 --set을 함께 쓸 수 없다")
    if (args.holdout or args.split) and not args.eval_set:
        parser.error("--holdout·--split은 --eval-set과 함께 쓴다")
    if not 0 <= args.threshold <= 1 or not all(0 <= t <= 1 for t in args.sweep):
        parser.error("임계값은 0과 1 사이다")
    args.sweep = tuple(sorted(set(args.sweep)))

    # 서버와 같은 설정으로 읽는다. 프로세스 환경변수가 있으면 그것을 먼저 쓴다
    settings = JevSettings(_env_file=args.env_file)
    try:
        settings.require()
    except AIConfigError as error:
        parser.error(f"{error} ({args.env_file})")
    client = JevClient(settings.base_url, settings.api_key.get_secret_value(), args.model, args.timeout)

    # eval_retrieval은 불러올 때 be/.env를 덮어 읽는다. 테스트가 이 파일을 불러와도 환경을 바꾸지 않게 여기서 불러온다
    from app.ai.scripts.eval_retrieval import _git

    report = run(args, client, _git())
    print("\n설정", json.dumps({k: report["settings"][k] for k in ("model", "served_models", "questions_version", "threshold")}, ensure_ascii=False))
    print("요약", json.dumps(report["summary"], ensure_ascii=False))
    for name, summary in report.get("by_set", report.get("by_split", {})).items():
        print(f"  {name}", json.dumps(summary, ensure_ascii=False))
    for name, missed in report.get("luna_caught_missed", {}).items():
        print(f"  {name} luna가 잡았는데 놓침", json.dumps(missed, ensure_ascii=False))
    for name, counts in report.get("breakdown", {}).items():
        print(f"  {name} 묶음별", json.dumps(counts["by_bundle"], ensure_ascii=False))
        print(f"  {name} 태그별", json.dumps(counts["by_tag"], ensure_ascii=False))
    print("임계값별 (홀드아웃 제외)\n  임계값  재현율  놓침     오개입률  오탐        둘 다 허용에서 조회  luna가 잡았는데 놓침")
    for row in report["threshold_sweep"]:
        print(
            f"  {row['threshold']:<6}  {row['recall']:<6}  {row['missed']:<7}  {row['false_alarm_per_100']!s:<8}"
            f"  {row['false_positive']:<10}  {row.get('either_lookup', ''):<18}  {row.get('luna_caught_missed', '')}"
        )
    print("지연", json.dumps(report["latency"], ensure_ascii=False))
    print("비용", json.dumps(report["cost"], ensure_ascii=False))
    if report["errors"]:
        print("오류", json.dumps(report["errors"], ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
