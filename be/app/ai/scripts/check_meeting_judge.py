"""회의 발화 판단(features/meeting)을 실제 ML API로 확인한다 (#114).

키가 필요해 CI에서 돌리지 않는다. 프롬프트·입력 형식·모델을 바꿨을 때 수동으로 실행하고
결과는 docs/meeting-evaluation.md 에 남긴다.

    cd be && uv run python app/ai/scripts/check_meeting_judge.py \\
        --script <측정폴더>/data/query_script.jsonl --stt <측정폴더>/results/query_stt.json \\
        [--baseline <측정폴더>/results/query_compare_v4.json] [--json 결과.json]

① 측정 문항(Whisper 텍스트)을 회의 순서대로 판단한다. 앞 발화는 같은 회의의 이전 발화다.
   균형 정확도·오탐·놓침과 판단 지연(trace.judge_ms)을 낸다.
   --baseline을 주면 측정 폴더에서 같은 프롬프트로 낸 판단·검색어와 발화별로 비교한다.
② 행사(event)를 넣었을 때와 뺐을 때 검색어가 어떻게 달라지는지 본다.

문항은 레포 밖 측정 폴더에 있다(#111, #123). 검색은 부르지 않는다.
검색과 근거 판단은 eval_retrieval.py --queries로 회의 검색어를 넣어 잰다(#72).
AI_* 는 --env-file(기본 be/.env)에서 읽고 키는 출력하지 않는다.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from statistics import median, quantiles

from dotenv import load_dotenv

from app.ai.errors import AIError
from app.ai.features.meeting.context import MEETING_TIMEZONE, PROMPT_VERSION
from app.ai.features.meeting.nodes import judge_utterance
from app.ai.features.meeting.schemas import (
    JudgeUtteranceRequest,
    MeetingEvent,
    MeetingUtterance,
)

# 측정 문항에는 발화 시각이 없어 회의 날짜 오후 2시부터 10초 간격으로 둔다
MEETING_START = time(14, 0)

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


async def _judge(request: JudgeUtteranceRequest) -> dict:
    try:
        result = await judge_utterance(request, lookup=NoSearch())
    except AIError as error:
        return {"error": f"{type(error).__name__}: {error}"}
    return {
        "pred": result.route == "RAG",
        "query": result.question or "",
        "judge_ms": result.trace.judge_ms,
        "model": result.trace.model,
    }


async def run_script(script: Path, stt: Path) -> list[dict]:
    rows = [json.loads(line) for line in script.read_text().splitlines() if line.strip()]
    heard = {r["id"]: r for r in json.loads(stt.read_text())["records"] if r["status"] == "completed"}
    records, history, meeting = [], [], None
    for row in rows:
        if row["id"] not in heard:
            continue
        if row["meeting"] != meeting:
            meeting, history = row["meeting"], []
        utterance = _utterance(len(history) + 1, heard[row["id"]]["heard"], row["meeting_date"])
        request = JudgeUtteranceRequest(
            meeting_id=row["meeting"], club_id="clb_check", utterance=utterance, context=tuple(history)
        )
        outcome = await _judge(request)
        records.append({"id": row["id"], "truth": row["needs_lookup"], "heard": utterance.text, **outcome})
        history.append(utterance)
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


def summarize(records: list[dict]) -> dict:
    done = [r for r in records if "error" not in r]
    pos = [r for r in done if r["truth"]]
    neg = [r for r in done if not r["truth"]]
    recall = sum(r["pred"] for r in pos) / len(pos) if pos else 0.0
    specificity = sum(not r["pred"] for r in neg) / len(neg) if neg else 0.0
    ms = sorted(r["judge_ms"] for r in done)
    return {
        "calls": len(records),
        "errors": len(records) - len(done),
        "balanced_accuracy": round((recall + specificity) / 2, 3),
        "false_positive": f"{sum(r['pred'] for r in neg)} / {len(neg)}",
        "missed": f"{sum(not r['pred'] for r in pos)} / {len(pos)}",
        "p50_s": round(median(ms) / 1000, 2) if ms else None,
        "p95_s": round(quantiles(ms, n=20)[18] / 1000, 2) if len(ms) >= 2 else None,
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


async def run(args) -> dict:
    print(f"① 측정 문항 판단 · 프롬프트 {PROMPT_VERSION}")
    records = await run_script(args.script, args.stt)
    report = {"prompt_version": PROMPT_VERSION, "summary": summarize(records)}
    if records and "model" in records[0]:
        report["model"] = records[0]["model"]
    if args.baseline:
        report["baseline"] = compare(records, args.baseline)
    print("\n② 행사 정보에 따른 검색어")
    report["events"] = await run_events()
    report["records"] = records
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path, required=True, help="측정 문항 (query_script.jsonl)")
    parser.add_argument("--stt", type=Path, required=True, help="Whisper 결과 (query_stt.json)")
    parser.add_argument("--baseline", type=Path, help="측정 폴더의 v4 결과 (query_compare_v4.json)")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    args = parser.parse_args()

    load_dotenv(args.env_file.resolve(), override=True)
    # 한 이벤트 루프에서 모두 돈다. asyncio.run을 여러 번 부르면 공유 HTTP 연결이 깨진다
    report = asyncio.run(run(args))

    print("\n요약", json.dumps(report["summary"], ensure_ascii=False))
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
