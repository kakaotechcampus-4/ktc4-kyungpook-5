"""판단 전용 모델(Laya)로 회의 판단 평가 문항을 판단한다 (#117).

학습 전 기본 모델과 학습한 모델을 같은 문항·같은 입력 글로 재서 비교하기 위한 스크립트다.
laya와 torch는 BE 의존성에 넣지 않는다. 잴 때만 붙인다. 키는 필요 없다.

    cd be && uv run --with laya==0.4.7 python app/ai/scripts/check_laya_judge.py \\
        [--model <저장소 또는 학습한 체크포인트 경로>] [--threads N] [--repeat 3] [--eval-set [--holdout]]
        [--threshold 0.5] [--sweep 0.5 0.7 0.9] [--json 결과.json]

- 문항: tests/fixtures/eval/meeting_judge.jsonl. luna(check_meeting_judge.py)와 같은 문항이다.
  이 문항은 학습 데이터에 넣지 않는다. 넣으면 학습 후 값이 의미가 없어진다.
  --eval-set이면 회의 판단 평가 세트(#115)를 같은 규칙(개발용만, --holdout이면 홀드아웃도)으로 고른다
- 입력 글은 luna와 같은 build_judge_input, 질문은 questions.py의 record_lookup이다.
  P(true)가 임계값(--threshold, 기본 0.5) 이상이면 조회로 본다. AUROC는 기준값과 관계없이 조회할 발화에 더 높은 확률을 줬는지 본다
- 임계값 표: 같은 확률로 임계값 후보(--sweep)마다 재현율·오개입률을 다시 센다. 홀드아웃은 넣지 않는다.
  임계값은 개발용에서 고르고, 홀드아웃은 고른 값을 확인하는 데만 쓴다
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


def run(args) -> dict:
    if args.threads:
        torch.set_num_threads(args.threads)
    path, key, groups, requests = eval_items(args)
    items = [(row, build_judge_input(request)) for row, request in requests]
    questions = judge_questions()
    revision = args.revision if args.revision is not None else (BASE_REVISION if args.model == BASE_MODEL else None)

    rss_before = _max_rss_mb()
    started = time.perf_counter()
    agent = laya.load(args.model, device="cpu", revision=revision)
    load_s = round(time.perf_counter() - started, 2)
    agent.predict(items[0][1], questions)  # 예열. 첫 호출은 느리다

    passes = []
    for _ in range(args.repeat):
        p_true, ms = [], []
        for _, state in items:
            started = time.perf_counter()
            answer = agent.predict(state, questions)["answers"][RECORD_LOOKUP]
            ms.append((time.perf_counter() - started) * 1000)
            p_true.append(answer["noul"])
        passes.append((p_true, ms))

    first = passes[0][0]
    records = []
    for (row, _), p in zip(items, first):
        pred = p >= args.threshold
        records.append({**eval_record(row), "p_true": round(p, 4), "pred": pred})
        print(f"  {'O' if pred == row['needs_lookup'] else 'X'} {row['id']:6} P={p:.3f}  {row['heard']}")

    ms = sorted(m for _, pass_ms in passes for m in pass_ms)
    return {
        "settings": {
            **_git(),
            "model": args.model,
            "revision": revision,
            "laya": laya.__version__,
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
            "questions_version": QUESTIONS_VERSION,
            "threshold": args.threshold,
            "eval": path.name,
            key: groups,
            "repeat": args.repeat,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "summary": summarize(records),
        f"by_{key}": {name: summarize([r for r in records if r[key] == name]) for name in groups},
        **({"breakdown": {name: breakdown([r for r in records if r["split"] == name]) for name in groups}}
           if key == "split" else {}),
        # 임계값은 홀드아웃을 보지 않고 고른다. 홀드아웃은 고른 값을 확인하는 데만 쓴다
        "threshold_sweep": threshold_sweep([r for r in records if r.get("split") != "holdout"], args.sweep),
        "latency": {
            "load_s": load_s,
            "p50_ms": round(median(ms), 1),
            "p95_ms": round(quantiles(ms, n=20)[18], 1),
            "max_ms": round(ms[-1], 1),
            # 회차마다 같은 입력에 같은 확률이 나왔는지. 0이면 판단 값은 한 번 재면 된다
            "max_p_diff_between_passes": round(
                max(abs(a - b) for p_true, _ in passes[1:] for a, b in zip(first, p_true)), 6
            ) if len(passes) > 1 else None,
        },
        "memory": {"max_rss_mb_before_load": rss_before, "max_rss_mb": _max_rss_mb()},
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=BASE_MODEL, help="Hugging Face 저장소 또는 학습한 체크포인트 경로")
    parser.add_argument("--revision", help=f"모델 커밋. 기본 모델이면 {BASE_REVISION[:7]}")
    parser.add_argument("--threads", type=int, help="torch CPU 스레드 수. 주지 않으면 torch 기본값")
    parser.add_argument("--repeat", type=int, default=3, help="지연을 재려고 문항 전체를 판단하는 횟수")
    parser.add_argument("--threshold", type=float, default=THRESHOLD, help=f"P(true)가 이 값 이상이면 조회로 본다. 기본 {THRESHOLD}")
    parser.add_argument("--sweep", type=float, nargs="+", default=SWEEP, help="임계값 표의 후보. 기본 0.05~0.95, 0.05 간격")
    add_eval_args(parser)
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
    for name, counts in report.get("breakdown", {}).items():
        print(f"  {name} 묶음별", json.dumps(counts["by_bundle"], ensure_ascii=False))
        print(f"  {name} 태그별", json.dumps(counts["by_tag"], ensure_ascii=False))
    print("임계값별 (홀드아웃 제외)\n  임계값  재현율  놓침     오개입률  오탐        둘 다 허용에서 조회")
    for row in report["threshold_sweep"]:
        print(
            f"  {row['threshold']:<6}  {row['recall']:<6}  {row['missed']:<7}  {row['false_alarm_per_100']!s:<8}"
            f"  {row['false_positive']:<10}  {row.get('either_lookup', '')}"
        )
    print("지연", json.dumps(report["latency"], ensure_ascii=False))
    print("메모리", json.dumps(report["memory"], ensure_ascii=False))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
