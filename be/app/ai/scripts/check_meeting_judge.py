"""회의 발화 판단(features/meeting)을 실제 ML API로 확인한다 (#114, #117).

키가 필요해 CI에서 돌리지 않는다. 프롬프트·입력 형식·모델을 바꿨을 때 수동으로 실행하고
결과는 docs/meeting-evaluation.md 에 남긴다.

    cd be && uv run python app/ai/scripts/check_meeting_judge.py \\
        [--set query --set pipeline ...] [--baseline <측정폴더>/results/query_compare_v4.json] [--json 결과.json]
    cd be && uv run python app/ai/scripts/check_meeting_judge.py --eval-set [--holdout] [--json 결과.json]

① 회의 판단 평가 문항(tests/fixtures/eval/meeting_judge.jsonl)을 회의 순서대로 판단한다.
   앞 발화는 같은 회의의 이전 발화다. 균형 정확도·재현율·특이도·정밀도·오탐·놓침·오개입률과 판단 지연(trace.judge_ms),
   호출당 토큰(입력·캐시·출력)과 판단 1,000회 비용을 문항 묶음별로 낸다.
   --baseline을 주면 측정 폴더에서 같은 프롬프트로 낸 판단·검색어와 발화별로 비교한다.
   --eval-set이면 회의 판단 평가 세트(meeting_judge_set.jsonl, #115)를 쓴다. 개발용만 재고, --holdout을 주면
   홀드아웃도 재서 따로 낸다. 오답을 묶음별·태그별로 센다.
② 행사(event)를 넣었을 때와 뺐을 때 검색어가 어떻게 달라지는지 본다. 평가 세트는 회의마다 행사를 이미 넣으므로 건너뛴다.

검색은 부르지 않는다. 검색과 근거 판단은 eval_retrieval.py --queries로 회의 검색어를 넣어 잰다(#72).
학습 전·후 Laya는 같은 문항을 check_laya_judge.py로 잰다.
AI_* 는 --env-file(기본 be/.env)에서 읽고 키는 출력하지 않는다.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from statistics import mean, median, quantiles

from dotenv import load_dotenv
from langchain_core.callbacks import get_usage_metadata_callback

from app.ai.errors import AIError
from app.ai.features.meeting.context import MEETING_TIMEZONE, PROMPT_VERSION
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.schemas import (
    JudgeUtteranceRequest,
    MeetingEvent,
    MeetingUtterance,
)

# 회의 판단 평가 문항(Laya 학습 전후 비교)과 평가 세트(#115). 형식은 tests/fixtures/eval/README.md
EVAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval"
EVAL_UTTERANCES = EVAL_DIR / "meeting_judge.jsonl"
EVAL_SET = EVAL_DIR / "meeting_judge_set.jsonl"
SETS = ("query", "pipeline", "vocative")
SPLITS = ("dev", "holdout")

# 평가 문항에는 발화 시각이 없어 회의 날짜 오후 2시부터 10초 간격으로 둔다
MEETING_START = time(14, 0)

# 게이트웨이 단가(원/100만 토큰). ML API 모델 페이지 2026-10-19 기준이다. 바뀌면 고친다.
# 캐시된 입력은 입력 토큰에 포함돼 오므로 입력 단가에서 빼고 캐시 단가로 센다
PRICE_KRW_PER_M = {"gpt-5.6-luna": {"input": 283, "cached": 28, "output": 1701}}

# 행사 정보가 검색어에 주는 영향. (행사 제목, 앞 발화, 방금 발화)
EVENT_CASES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("2026 봄 MT", (), "이번 거 참가비 상한이 회칙에 있었나?"),
    ("2026 봄 MT", ("숙소부터 정하죠",), "작년에는 거기 숙소비 얼마 들었죠?"),
    ("2026 신입생 환영회", (), "작년엔 몇 명 왔었지?"),
)


class NoSearch:
    """검색을 부르지 않는다. 판단과 검색어만 본다"""

    answer_prompt_version = "no-search"

    async def search(self, request):
        return ()

    async def answer(self, request, chunks):
        return None


def _utterance(seq: int, text: str, meeting_date: str) -> MeetingUtterance:
    day = datetime.fromisoformat(meeting_date).date()
    at = datetime.combine(day, MEETING_START, MEETING_TIMEZONE) + timedelta(seconds=10 * seq)
    return MeetingUtterance(
        utterance_id=f"u-{seq}", seq=seq, text=text, started_at=at, ended_at=at + timedelta(seconds=3)
    )


def load_requests(
    path: Path = EVAL_UTTERANCES, sets: tuple[str, ...] = SETS, splits: tuple[str, ...] = SPLITS
) -> list[tuple[dict, JudgeUtteranceRequest]]:
    """평가 문항을 회의 순서대로 판단 요청으로 만든다. 앞 발화는 같은 회의의 이전 발화(Whisper 텍스트)다.

    `sets`는 평가 문항의 묶음(`set`), `splits`는 평가 세트의 개발용·홀드아웃(`split`)으로 거른다.
    둘 다 회의 단위로 붙어 있어 걸러도 앞 발화가 끊기지 않는다. 그 칸이 없는 파일에는 쓰지 않는다.
    """
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    requests, history, meeting = [], [], None
    for row in rows:
        if row.get("set", sets[0]) not in sets or row.get("split", splits[0]) not in splits:
            continue
        if row["meeting"] != meeting:
            meeting, history = row["meeting"], []
        utterance = _utterance(len(history) + 1, row["heard"], row["meeting_date"])
        event = MeetingEvent(event_id=f"evt_{row['meeting']}", title=row["event"]) if row.get("event") else None
        request = JudgeUtteranceRequest(
            meeting_id=row["meeting"], club_id="clb_check", utterance=utterance, context=tuple(history), event=event
        )
        requests.append((row, request))
        history.append(utterance)
    return requests


async def _judge(request: JudgeUtteranceRequest) -> dict:
    with get_usage_metadata_callback() as usage:
        try:
            result = await judge_utterance(request, lookup=NoSearch())
        except AIError as error:
            return {"error": f"{type(error).__name__}: {error}"}
    # 재시도가 있었다면 모든 호출의 토큰을 더한다. 실제로 내는 값이기 때문이다
    tokens = {"input": 0, "cached": 0, "output": 0, "reasoning": 0}
    for item in usage.usage_metadata.values():
        tokens["input"] += item.get("input_tokens", 0)
        tokens["cached"] += item.get("input_token_details", {}).get("cache_read", 0) or 0
        tokens["output"] += item.get("output_tokens", 0)
        tokens["reasoning"] += item.get("output_token_details", {}).get("reasoning", 0) or 0
    return {
        "pred": result.route == "RAG",
        "query": result.question or "",
        "judge_ms": result.trace.judge_ms,
        "model": result.trace.model,
        "tokens": tokens,
    }


def eval_record(row: dict) -> dict:
    """문항 하나의 결과 기록에 남길 문항 정보. 판단 값은 부르는 쪽이 더한다"""
    record = {"id": row["id"], "truth": row["needs_lookup"], "heard": row["heard"]}
    for key in ("set", "split", "bundle", "category", "either"):
        if key in row:
            record[key] = row[key]
    return record


async def run_eval(items: list[tuple[dict, JudgeUtteranceRequest]]) -> list[dict]:
    records = []
    for row, request in items:
        outcome = await _judge(request)
        records.append({**eval_record(row), **outcome})
        mark = "!" if "error" in outcome else ("O" if outcome["pred"] == row["needs_lookup"] else "X")
        print(f"  {mark} {row['id']:6} {outcome.get('judge_ms', '-'):>5}ms  {outcome.get('query') or outcome.get('error', '')}")
    return records


async def run_events() -> list[dict]:
    records = []
    for title, before, text in EVENT_CASES:
        context = tuple(_utterance(i + 1, t, "2026-03-05") for i, t in enumerate(before))
        utterance = _utterance(len(context) + 1, text, "2026-03-05")
        event = MeetingEvent(event_id="evt_check", title=title)
        pair = {}
        for name, value in (("행사 없음", None), ("행사 있음", event)):
            request = JudgeUtteranceRequest(
                meeting_id="mtg_event", club_id="clb_check", utterance=utterance, context=context, event=value
            )
            pair[name] = await _judge(request)
        records.append({"event": title, "text": text, **pair})
        print(f"  [{title}] {text}")
        for name, outcome in pair.items():
            print(f"      {name}: {outcome.get('query') or outcome.get('error') or '(조회 아님)'}")
    return records


def _cost_per_1000(model: str | None, tokens: dict) -> float | None:
    """호출당 평균 토큰으로 판단 1,000회 비용(원). 단가를 모르는 모델이면 None"""
    price = PRICE_KRW_PER_M.get(model or "")
    if price is None:
        return None
    won = (
        (tokens["input"] - tokens["cached"]) * price["input"]
        + tokens["cached"] * price["cached"]
        + tokens["output"] * price["output"]
    ) / 1_000_000
    return round(won * 1000, 1)


def confusion(records: list[dict]) -> dict:
    """판단(`pred`)과 정답(`truth`)으로 낸 지표. luna와 Laya가 같은 식으로 센다.

    - 정밀도: 조회로 판단한 것 중 실제로 조회할 발화의 비율. 조회로 판단한 것이 없으면 None
    - 오개입률: 조회 아닌 발화 100개당 조회로 판단한 수. 회의 중 화면이 쓸데없이 뜨는 빈도다.
      시간당 오개입은 여기에 실제 회의의 시간당 발화 수를 곱해야 해서 여기서 내지 않는다
    - 둘 다 허용(`either`)인 문항은 채점하지 않고, 조회로 판단한 수만 따로 센다. 호출이 드는 횟수라서다
    """
    either = [r for r in records if r.get("either")]
    scored = [r for r in records if not r.get("either")]
    pos = [r for r in scored if r["truth"]]
    neg = [r for r in scored if not r["truth"]]
    hit = sum(r["pred"] for r in pos)
    false_positive = sum(r["pred"] for r in neg)
    recall = hit / len(pos) if pos else 0.0
    specificity = 1 - false_positive / len(neg) if neg else 0.0
    return {
        "balanced_accuracy": round((recall + specificity) / 2, 3),
        "recall": round(recall, 3),
        "specificity": round(specificity, 3),
        "precision": round(hit / (hit + false_positive), 3) if hit + false_positive else None,
        "false_positive": f"{false_positive} / {len(neg)}",
        "missed": f"{len(pos) - hit} / {len(pos)}",
        "false_alarm_per_100": round(100 * false_positive / len(neg), 1) if neg else None,
        **({"either_lookup": f"{sum(r['pred'] for r in either)} / {len(either)}"} if either else {}),
    }


def breakdown(records: list[dict]) -> dict:
    """묶음별·태그별로 문항 수와 틀린 수를 센다. 무엇을 놓치고 어디서 잘못 끼어드는지 본다.
    둘 다 허용인 문항은 문항 수에만 들어가고 틀린 수에는 들어가지 않는다"""
    def count(groups: dict[str, list[dict]]) -> dict:
        return {
            name: {"items": len(rows), "wrong": sum(r["pred"] != r["truth"] for r in rows if not r.get("either"))}
            for name, rows in sorted(groups.items())
        }

    bundles: dict[str, list[dict]] = {}
    tags: dict[str, list[dict]] = {}
    for record in records:
        if "bundle" in record:
            bundles.setdefault(record["bundle"], []).append(record)
        for tag in record.get("category", ()):
            tags.setdefault(tag, []).append(record)
    return {"by_bundle": count(bundles), "by_tag": count(tags)}


def summarize(records: list[dict]) -> dict:
    done = [r for r in records if "error" not in r]
    ms = sorted(r["judge_ms"] for r in done)
    tokens = {
        key: round(mean(r["tokens"][key] for r in done), 1) if done else None
        for key in ("input", "cached", "output", "reasoning")
    }
    return {
        "calls": len(records),
        "errors": len(records) - len(done),
        **confusion(done),
        "p50_s": round(median(ms) / 1000, 2) if ms else None,
        "p95_s": round(quantiles(ms, n=20)[18] / 1000, 2) if len(ms) >= 2 else None,
        "tokens_per_call": tokens,
        "krw_per_1000": _cost_per_1000(done[0]["model"], tokens) if done else None,
    }


def compare(records: list[dict], baseline: Path) -> dict:
    """측정 폴더의 v4 결과(1회차)와 발화별로 비교한다"""
    data = json.loads(baseline.read_text())
    before = {
        r["id"]: r
        for r in data["records"]
        if r["condition"] == "v4_ctx4" and r["rep"] == 0 and not r.get("error")
    }
    pairs = [(r, before[r["id"]]) for r in records if "error" not in r and r["id"] in before]
    same_pred = sum(r["pred"] == b["pred"] for r, b in pairs)
    both = [(r, b) for r, b in pairs if r["pred"] and b["pred"]]
    same_query = sum(r["query"] == b["query"] for r, b in both)
    changed = [
        {"id": r["id"], "repo": r["query"], "baseline": b["query"]}
        for r, b in both
        if r["query"] != b["query"]
    ]
    flipped = [r["id"] for r, b in pairs if r["pred"] != b["pred"]]
    return {
        "compared": len(pairs),
        "same_judgment": f"{same_pred} / {len(pairs)}",
        "judgment_flipped": flipped,
        "same_query": f"{same_query} / {len(both)}",
        "query_changed": changed,
    }


def eval_items(args) -> tuple[Path, str, tuple[str, ...], list[tuple[dict, JudgeUtteranceRequest]]]:
    """잴 파일과 나눌 기준(묶음 또는 개발용·홀드아웃)과 문항. luna와 Laya가 같은 인자로 같은 문항을 고른다"""
    if args.eval_set:
        groups = SPLITS if args.holdout else ("dev",)
        return EVAL_SET, "split", groups, load_requests(EVAL_SET, splits=groups)
    groups = tuple(args.set or SETS)
    return EVAL_UTTERANCES, "set", groups, load_requests(EVAL_UTTERANCES, sets=groups)


async def run(args) -> dict:
    # eval_retrieval은 불러올 때 .env를 읽는다. 테스트가 이 파일을 불러와도 환경을 바꾸지 않게 여기서 불러온다
    from app.ai.scripts.eval_retrieval import _git

    path, key, groups, items = eval_items(args)
    print(f"① {path.name} 판단 · 프롬프트 {PROMPT_VERSION} · {', '.join(groups)}")
    records = await run_eval(items)
    report = {
        "settings": {**_git(), "eval": path.name, key: groups},
        "prompt_version": PROMPT_VERSION,
        "summary": summarize(records),
        f"by_{key}": {name: summarize([r for r in records if r[key] == name]) for name in groups},
    }
    if args.eval_set:
        done = [r for r in records if "error" not in r]
        report["breakdown"] = {name: breakdown([r for r in done if r["split"] == name]) for name in groups}
    if records and "model" in records[0]:
        report["model"] = records[0]["model"]
    if args.baseline:
        report["baseline"] = compare(records, args.baseline)
    if not args.eval_set:
        print("\n② 행사 정보에 따른 검색어")
        report["events"] = await run_events()
    report["records"] = records
    return report


def add_eval_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", action="append", choices=SETS, help="잴 문항 묶음. 여러 번 줄 수 있다. 기본은 전부")
    parser.add_argument("--eval-set", action="store_true", help="회의 판단 평가 세트(#115)를 잰다. 기본은 개발용만")
    parser.add_argument("--holdout", action="store_true", help="평가 세트의 홀드아웃도 잰다. 기록에 남길 측정에서만 켠다")


def main() -> int:
    parser = argparse.ArgumentParser()
    add_eval_args(parser)
    parser.add_argument("--baseline", type=Path, help="측정 폴더의 v4 결과 (query_compare_v4.json)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    args = parser.parse_args()
    if args.eval_set and (args.set or args.baseline):
        parser.error("--eval-set에는 --set·--baseline을 함께 쓸 수 없다")
    if args.holdout and not args.eval_set:
        parser.error("--holdout은 --eval-set과 함께 쓴다")

    load_dotenv(args.env_file.resolve(), override=True)
    # 한 이벤트 루프에서 모두 돈다. asyncio.run을 여러 번 부르면 공유 HTTP 연결이 깨진다
    report = asyncio.run(run(args))

    print("\n요약", json.dumps(report["summary"], ensure_ascii=False))
    for name, summary in report.get("by_set", report.get("by_split", {})).items():
        print(f"  {name}", json.dumps(summary, ensure_ascii=False))
    for name, counts in report.get("breakdown", {}).items():
        print(f"  {name} 묶음별", json.dumps(counts["by_bundle"], ensure_ascii=False))
        print(f"  {name} 태그별", json.dumps(counts["by_tag"], ensure_ascii=False))
    if "baseline" in report:
        shown = {k: v for k, v in report["baseline"].items() if k != "query_changed"}
        print("측정 폴더와 비교", json.dumps(shown, ensure_ascii=False))
        for item in report["baseline"]["query_changed"]:
            print(f"  {item['id']}: 측정 {item['baseline']!r} → 레포 {item['repo']!r}")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
