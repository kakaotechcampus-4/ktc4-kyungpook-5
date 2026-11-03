"""판단 전용 모델(Laya)로 회의 판단 평가 문항을 판단한다 (#117).

학습 전 기본 모델과 학습한 모델을 같은 문항·같은 입력 글로 재서 비교하기 위한 스크립트다.
laya와 torch는 BE 의존성에 넣지 않는다. 잴 때만 붙인다. 키는 필요 없다.

    cd be && uv run --with laya==0.4.7 python app/ai/scripts/check_laya_judge.py \\
        [--model <저장소 또는 학습한 체크포인트 경로> ...] [--threads N] [--repeat 3] [--eval-set [--holdout]]
        [--threshold 0.5] [--sweep 0.5 0.7 0.9] [--luna luna결과.json] [--json 결과.json]

- 문항: tests/fixtures/eval/meeting_judge.jsonl. luna(check_meeting_judge.py)와 같은 문항이다.
  이 문항은 학습 데이터에 넣지 않는다. 넣으면 학습 후 값이 의미가 없어진다.
  --eval-set이면 회의 판단 평가 세트(#115)를 같은 규칙(개발용만, --holdout이면 홀드아웃도)으로 고른다
- 입력 글은 luna와 같은 build_judge_input, 질문은 questions.py의 record_lookup이다.
  P(true)가 임계값(--threshold, 기본 0.5) 이상이면 조회로 본다. AUROC는 기준값과 관계없이 조회할 발화에 더 높은 확률을 줬는지 본다
- 임계값 표: 같은 확률로 임계값 후보(--sweep)마다 재현율·오개입률을 다시 센다. 홀드아웃은 넣지 않는다.
  임계값은 개발용에서 고르고, 홀드아웃은 고른 값을 확인하는 데만 쓴다
- --model에 체크포인트를 여러 개 주면 발화마다 모두 판단해 조회 확률을 평균한다(세 시드 평균, #117).
  임계값과 AUROC는 평균으로 보고, 모델별 확률은 기록에만 남긴다. 지연은 발화 하나를 모든 모델이 판단한 시간이다
- --luna에 같은 문항을 잰 luna 결과(check_meeting_judge.py --json)를 주면 luna가 잡은 조회 중 놓친 것을 센다.
  1단계 기준이 "luna가 잡은 조회를 하나도 놓치지 않음"이라서다. 정답은 luna 결과가 아니라 지금 평가 문항에서 읽는다
- CPU에서만 돈다. 배포 서버에 GPU가 없기 때문이다
- 지연: 예열 1회 뒤 문항 전체를 --repeat번 판단한다. 판단 값은 첫 회를 쓰고, 회차마다 값이 같은지도 낸다
- 모델은 Hugging Face 캐시에서 읽는다. 처음 한 번은 받는다(기본 모델 644MB)
"""

import argparse
import json
import resource
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import median, quantiles

try:
    import laya
    import torch
except ImportError:
    sys.exit("laya가 없습니다. cd be && uv run --with laya==0.4.7 python app/ai/scripts/check_laya_judge.py")

from app.ai.features.meeting.context import MEETING_TIMEZONE, build_judge_input
from app.ai.features.meeting.questions import (
    QUESTIONS_VERSION,
    RECORD_LOOKUP,
    judge_questions,
)
from app.ai.scripts.check_meeting_judge import (
    add_eval_args,
    breakdown,
    confusion,
    eval_items,
    eval_record,
    threshold_sweep,
)
from app.ai.scripts.eval_retrieval import _git

# 학습 전 기본 모델. 한국어가 들어 있는 multilingual에서 학습을 시작한다(#117)
BASE_MODEL = "convaiinnovations/laya-multilingual"
# laya 0.4.7이 검토한 커밋으로 고정한다(laya.PINNED_REVISIONS). 최신 main과 다를 수 있다
BASE_REVISION = "e4e9ddf21a7b1903b7acffd8814ad4307bf63a67"
THRESHOLD = 0.5
# 임계값 표의 후보. 조회 비율이 높은 데이터로 배우면 확률이 조회 쪽으로 기울어 0.5보다 높은 값을 고를 수 있다
SWEEP = tuple(round(0.05 * i, 2) for i in range(1, 20))


def _max_rss_mb() -> float:
    """지금까지의 최대 메모리. macOS는 바이트, Linux는 KB로 준다"""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1e6 if sys.platform == "darwin" else 1e3), 1)


def auroc(scores: list[float], truths: list[bool]) -> float | None:
    """조회할 발화 하나와 아닌 발화 하나를 뽑았을 때 조회할 쪽 확률이 더 높을 비율. 같으면 반으로 센다"""
    pos = [s for s, t in zip(scores, truths) if t]
    neg = [s for s, t in zip(scores, truths) if not t]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def summarize(records: list[dict]) -> dict:
    # 둘 다 허용인 문항은 채점하지 않으므로 확률의 순서를 볼 때도 뺀다
    scored = [r for r in records if not r.get("either")]
    pos = [r for r in scored if r["truth"]]
    neg = [r for r in scored if not r["truth"]]
    return {
        "items": len(records),
        **confusion(records),
        "auroc": auroc([r["p_true"] for r in scored], [r["truth"] for r in scored]),
        "p_true_mean": {
            "lookup": round(sum(r["p_true"] for r in pos) / len(pos), 3) if pos else None,
            "no_lookup": round(sum(r["p_true"] for r in neg) / len(neg), 3) if neg else None,
        },
    }


def luna_caught(path: Path) -> set[str]:
    """luna가 조회로 판단한 문항 id. 정답과 맞았는지는 부르는 쪽이 지금 평가 문항의 정답으로 가린다"""
    return {r["id"] for r in json.loads(path.read_text())["records"] if r.get("pred")}


def luna_missed(records: list[dict], caught: set[str], threshold: float | None = None) -> dict:
    """조회할 발화 중 luna가 잡았는데 Laya가 놓친 것. 둘 다 허용은 채점하지 않으므로 뺀다.
    threshold를 주면 그 임계값으로 다시 판단한다(임계값 표)"""
    target = [r for r in records if r["truth"] and not r.get("either") and r["id"] in caught]
    missed = [r["id"] for r in target if not (r["p_true"] >= threshold if threshold is not None else r["pred"])]
    return {"missed": f"{len(missed)} / {len(target)}", "ids": missed}


def _revision(args, model: str) -> str | None:
    if args.revision is not None:
        return args.revision
    return BASE_REVISION if model == BASE_MODEL else None


def run(args) -> dict:
    if args.threads:
        torch.set_num_threads(args.threads)
    path, key, groups, requests = eval_items(args)
    items = [(row, build_judge_input(request)) for row, request in requests]
    questions = judge_questions()
    revisions = [_revision(args, model) for model in args.model]

    rss_before = _max_rss_mb()
    started = time.perf_counter()
    agents = [laya.load(model, device="cpu", revision=rev) for model, rev in zip(args.model, revisions)]
    load_s = round(time.perf_counter() - started, 2)
    for agent in agents:
        agent.predict(items[0][1], questions)  # 예열. 첫 호출은 느리다

    passes = []
    for _ in range(args.repeat):
        p_models, ms = [], []
        for _, state in items:
            # 실제로 쓸 때처럼 발화 하나를 모든 모델이 차례로 판단한 시간을 잰다
            started = time.perf_counter()
            p_models.append([agent.predict(state, questions)["answers"][RECORD_LOOKUP]["noul"] for agent in agents])
            ms.append((time.perf_counter() - started) * 1000)
        passes.append((p_models, ms))

    def average(p_models: list[list[float]]) -> list[float]:
        return [sum(ps) / len(ps) for ps in p_models]

    first = average(passes[0][0])
    records = []
    for (row, _), p, ps in zip(items, first, passes[0][0]):
        pred = p >= args.threshold
        # 모델이 여럿이면 시드마다 확률이 얼마나 갈리는지 볼 수 있게 모델별 확률도 남긴다
        each = {"p_models": [round(x, 4) for x in ps]} if len(agents) > 1 else {}
        records.append({**eval_record(row), "p_true": round(p, 4), **each, "pred": pred})
        detail = "  (" + " / ".join(f"{x:.2f}" for x in ps) + ")" if len(agents) > 1 else ""
        print(f"  {'O' if pred == row['needs_lookup'] else 'X'} {row['id']:6} P={p:.3f}{detail}  {row['heard']}")

    caught = luna_caught(args.luna) if args.luna else None
    sweep_records = [r for r in records if r.get("split") != "holdout"]
    sweep = threshold_sweep(sweep_records, args.sweep)
    if caught is not None:
        for row in sweep:
            row["luna_caught_missed"] = luna_missed(sweep_records, caught, row["threshold"])["missed"]

    ms = sorted(m for _, pass_ms in passes for m in pass_ms)
    return {
        "settings": {
            **_git(),
            # 모델 하나면 예전 결과와 같은 모양(문자열)으로 남긴다
            "model": args.model[0] if len(args.model) == 1 else args.model,
            "revision": revisions[0] if len(revisions) == 1 else revisions,
            "laya": laya.__version__,
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
            "questions_version": QUESTIONS_VERSION,
            "threshold": args.threshold,
            "luna": str(args.luna) if args.luna else None,
            "eval": path.name,
            key: groups,
            "repeat": args.repeat,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "summary": summarize(records),
        f"by_{key}": {name: summarize([r for r in records if r[key] == name]) for name in groups},
        **({"luna_caught_missed": {name: luna_missed([r for r in records if r[key] == name], caught) for name in groups}}
           if caught is not None else {}),
        **({"breakdown": {name: breakdown([r for r in records if r["split"] == name]) for name in groups}}
           if key == "split" else {}),
        # 임계값은 홀드아웃을 보지 않고 고른다. 홀드아웃은 고른 값을 확인하는 데만 쓴다
        "threshold_sweep": sweep,
        "latency": {
            "load_s": load_s,
            "p50_ms": round(median(ms), 1),
            "p95_ms": round(quantiles(ms, n=20)[18], 1),
            "max_ms": round(ms[-1], 1),
            # 회차마다 같은 입력에 같은 확률이 나왔는지. 0이면 판단 값은 한 번 재면 된다
            "max_p_diff_between_passes": round(
                max(abs(a - b) for p_models, _ in passes[1:] for a, b in zip(first, average(p_models))), 6
            ) if len(passes) > 1 else None,
        },
        "memory": {"max_rss_mb_before_load": rss_before, "max_rss_mb": _max_rss_mb()},
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", nargs="+", default=[BASE_MODEL],
        help="Hugging Face 저장소 또는 학습한 체크포인트 경로. 여러 개면 조회 확률을 평균한다",
    )
    parser.add_argument("--revision", help=f"모델 커밋. 기본 모델이면 {BASE_REVISION[:7]}")
    parser.add_argument("--threads", type=int, help="torch CPU 스레드 수. 주지 않으면 torch 기본값")
    parser.add_argument("--repeat", type=int, default=3, help="지연을 재려고 문항 전체를 판단하는 횟수")
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"P(true)가 이 값 이상이면 조회로 본다. 기본 {THRESHOLD}")
    parser.add_argument("--sweep", type=float, nargs="+", default=SWEEP, help="임계값 표의 후보. 기본 0.05~0.95, 0.05 간격")
    add_eval_args(parser)
    parser.add_argument("--luna", type=Path, help="같은 문항을 잰 luna 결과. luna가 잡은 조회 중 놓친 것을 센다")
    parser.add_argument("--json", type=Path, help="결과를 저장할 파일")
    args = parser.parse_args()
    if args.eval_set and args.set:
        parser.error("--eval-set에는 --set을 함께 쓸 수 없다")
    if args.holdout and not args.eval_set:
        parser.error("--holdout은 --eval-set과 함께 쓴다")
    if not 0 <= args.threshold <= 1 or not all(0 <= t <= 1 for t in args.sweep):
        parser.error("임계값은 0과 1 사이다")
    args.sweep = tuple(sorted(set(args.sweep)))

    report = run(args)
    print("\n설정", json.dumps({k: report["settings"][k] for k in ("model", "revision", "threads", "questions_version")}, ensure_ascii=False))
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
    print("메모리", json.dumps(report["memory"], ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
