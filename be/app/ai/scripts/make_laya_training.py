"""검수한 회의 판단으로 판단 전용 모델(Laya)의 학습 파일을 만든다 (#117).

    cd be && uv run python app/ai/scripts/make_laya_training.py --reviewed 검수.jsonl --out 학습.jsonl \\
        [--holdout-extra 새_홀드아웃.jsonl ...] [--eval-out 개발용.jsonl] [--report 보고.json]

순서는 검수 결과 → 평가 문항과 겹침 검사 → 학습 줄 → 조회 비율 확인 → JSONL이다(architecture.md 4·6단계).

- 검수 결과: 한 줄에 ReviewedDecision(training.py) 하나를 JSON으로 적은 파일
- 겹침 검사: 방금 발화를 평가 문항 110개, 평가 세트 200건, --holdout-extra의 대본·판단 입력 글과 견준다.
  공백과 문장부호를 뺀 글자가 같거나 임베딩 코사인이 0.85 이상이면 겹침이다. 그 글자가 6자 이하면 보지 않는다.
  입력 글 전체(앞 발화·회의 날짜 포함)가 평가 문항과 같으면 짧은 말이어도 겹침이다. 겹친 판단은 학습 줄로 바꾸기 전에 뺀다
- 조회 비율: 학습 파일의 조회 비율을 25% 안팎으로 맞춘다. 맞추려면 어느 쪽 줄을 몇 개 더 넣어야 하는지 알려 줄 뿐 고치지 않는다
- --eval-out: laya-train --eval에 넣을 평가 세트 개발용. 홀드아웃은 넣지 않는다. --eval은 학습 전후 점수를 내기 때문이다

평가 쪽 문장의 임베딩은 eval_retrieval.py와 같은 캐시(scripts/.cache/embeddings.json)에 두고 다시 쓴다.
학습 문장은 실행마다 임베딩한다. 임베딩 키(AI_EMBEDDING_*)는 be/.env에서 읽는다. 키는 출력하지 않는다.
"""

import argparse
import asyncio
import json
import math
import operator
import re
import sys
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from datetime import datetime
from pathlib import Path

from app.ai.features.meeting.context import MEETING_TIMEZONE, build_judge_input
from app.ai.features.meeting.questions import QUESTIONS_VERSION, RECORD_LOOKUP, judge_questions
from app.ai.features.meeting.training import ReviewedDecision, export_training_lines, to_jsonl
from app.ai.scripts.check_meeting_judge import EVAL_SET, EVAL_UTTERANCES, load_requests

# 겹침 기준. 거의 같은 말이 0.88~0.98, 대상이 다른 말이 0.61~0.73이었다(2026-10-20, architecture.md 6단계)
SIMILAR_COSINE = 0.85
# 공백·문장부호를 뺀 글자가 이 길이 이하인 맞장구·진행 말은 어느 회의에나 나와서 보지 않는다
SHORT_CHARS = 6
# 걸린 판단이 이 비율을 넘으면 대본을 쓰는 방식을 점검한다
OVERLAP_ALERT = 0.05
LOOKUP_TARGET = 0.25

Embed = Callable[[Sequence[str]], Awaitable[Sequence[Sequence[float]]]]


def normalize(text: str) -> str:
    """공백과 문장부호를 뺀 글자. "작년 회비, 얼마였지?"와 "작년회비 얼마였지"는 같다"""
    return re.sub(r"[\W_]+", "", text)


def load_reviewed(path: Path) -> list[ReviewedDecision]:
    return [
        ReviewedDecision.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def eval_sentences(paths: Iterable[Path]) -> list[tuple[str, str]]:
    """평가 쪽 (문항 id, 문장). 대본(spoken)과 판단 입력(heard)을 모두 넣고 같은 문장은 한 번만 둔다"""
    seen: dict[str, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for text in (row["spoken"], row["heard"]):
                seen.setdefault(text, row["id"])
    return [(item_id, text) for text, item_id in seen.items()]


def eval_states(paths: Iterable[Path]) -> dict[str, str]:
    """평가 쪽 입력 글 전체 → 문항 id. 앞 발화와 회의 날짜까지 같은지 본다"""
    return {build_judge_input(request): row["id"] for path in paths for row, request in load_requests(path)}


def _unit(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


async def find_overlaps(
    decisions: Sequence[ReviewedDecision],
    sentences: Sequence[tuple[str, str]],
    states: dict[str, str],
    embed: Embed,
) -> list[dict]:
    """평가 문항과 겹치는 판단. 판단마다 처음 걸린 기준 하나만 적는다

    kind: state(입력 글 전체가 같음), same(글자가 같음), similar(임베딩 코사인 0.85 이상)
    """
    overlaps, pending = [], []
    by_text = {normalize(text): (item_id, text) for item_id, text in sentences}
    for decision in decisions:
        text = decision.request.utterance.text
        state = build_judge_input(decision.request)
        found = None
        if state in states:
            found = {"kind": "state", "eval_id": states[state]}
        elif len(normalize(text)) <= SHORT_CHARS:
            continue
        elif normalize(text) in by_text:
            item_id, eval_text = by_text[normalize(text)]
            found = {"kind": "same", "eval_id": item_id, "eval_text": eval_text}
        if found:
            overlaps.append({"decision_id": decision.decision_id, "text": text, **found})
        else:
            pending.append(decision)
    if not pending or not sentences:
        return overlaps

    # 학습 문장끼리는 견주지 않는다. 같은 문장은 한 번만 임베딩한다
    texts = list(dict.fromkeys(d.request.utterance.text for d in pending))
    eval_vectors = [_unit(v) for v in await embed([text for _, text in sentences])]
    train_vectors = dict(zip(texts, (_unit(v) for v in await embed(texts)), strict=True))
    for decision in pending:
        text = decision.request.utterance.text
        vector = train_vectors[text]
        cosine, index = max(
            (sum(map(operator.mul, vector, other)), i) for i, other in enumerate(eval_vectors)
        )
        if cosine >= SIMILAR_COSINE:
            item_id, eval_text = sentences[index]
            overlaps.append({
                "decision_id": decision.decision_id, "text": text, "kind": "similar",
                "eval_id": item_id, "eval_text": eval_text, "cosine": round(cosine, 3),
            })
    return overlaps


def lookup_balance(lines: Sequence[dict]) -> dict:
    """학습 줄의 조회 비율과, 25%에 맞추려면 더 넣을 줄 수. 같은 줄을 복제해 맞추지 않는다"""
    total = len(lines)
    lookups = sum(line["expected"][RECORD_LOOKUP] for line in lines)
    ratio = lookups / total if total else None
    # (조회) / (전체 + x) = 25% 이면 평범한 말 x줄, (조회 + x) / (전체 + x) = 25% 이면 조회 x줄
    add_plain = max(0, math.ceil(lookups / LOOKUP_TARGET - total))
    add_lookup = max(0, math.ceil((LOOKUP_TARGET * total - lookups) / (1 - LOOKUP_TARGET)))
    return {
        "lines": total,
        "lookup": lookups,
        "ratio": round(ratio, 3) if ratio is not None else None,
        "target": LOOKUP_TARGET,
        "add_plain_to_target": add_plain,
        "add_lookup_to_target": add_lookup,
    }


def eval_lines(path: Path = EVAL_SET) -> list[dict]:
    """laya-train --eval에 넣을 평가 세트 개발용. 둘 다 허용인 문항은 채점하지 않으므로 뺀다"""
    return [
        {
            "state": build_judge_input(request),
            "questions": judge_questions(),
            "expected": {RECORD_LOOKUP: row["needs_lookup"]},
        }
        for row, request in load_requests(path, splits=("dev",))
        if not row.get("either")
    ]


async def build(decisions: Sequence[ReviewedDecision], eval_paths: Sequence[Path], embed: Embed) -> dict:
    sentences = eval_sentences(eval_paths)
    overlaps = await find_overlaps(decisions, sentences, eval_states(eval_paths), embed)
    removed = {overlap["decision_id"] for overlap in overlaps}
    export = export_training_lines(d for d in decisions if d.decision_id not in removed)
    return {
        "export": export,
        "report": {
            "questions_version": QUESTIONS_VERSION,
            "decisions": len(decisions),
            "eval_files": [path.name for path in eval_paths],
            "eval_sentences": len(sentences),
            "overlap": {
                "removed": len(removed),
                "ratio": round(len(removed) / len(decisions), 3) if decisions else None,
                "by_kind": {
                    kind: sum(o["kind"] == kind for o in overlaps) for kind in ("state", "same", "similar")
                },
                "items": overlaps,
            },
            "export": {
                "needs_review": list(export.needs_review),
                "either": list(export.either),
                "three_way": list(export.three_way),
                "unreviewed": list(export.unreviewed),
                "merged": export.merged,
            },
            "balance": lookup_balance(export.lines),
        },
    }


def _cached_embed() -> tuple[Embed, Callable[[], None], str]:
    """평가 쪽 문장은 캐시에서 꺼내고, 없는 것만 부른다. eval_retrieval.py와 같은 키를 쓴다"""
    from app.ai.config import get_settings
    from app.ai.llm import EMBEDDING_DIMENSIONS, aembed_texts, build_embeddings
    from app.ai.scripts.eval_retrieval import EMBEDDING_CACHE, _hash, _load, _save

    settings = get_settings()
    model = build_embeddings(settings)
    cache = _load(EMBEDDING_CACHE)

    def key(text: str) -> str:
        return _hash(settings.embedding_model, str(EMBEDDING_DIMENSIONS), text)

    async def embed(texts: Sequence[str]) -> list[tuple[float, ...]]:
        missing = list(dict.fromkeys(t for t in texts if key(t) not in cache))
        if missing:
            for text, vector in zip(missing, await aembed_texts(missing, model=model), strict=True):
                cache[key(text)] = list(vector)
        return [tuple(cache[key(t)]) for t in texts]

    return embed, lambda: _save(EMBEDDING_CACHE, cache), settings.embedding_model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewed", type=Path, required=True, help="검수 결과. 한 줄에 ReviewedDecision 하나")
    parser.add_argument("--out", type=Path, required=True, help="laya-train --data에 넣을 학습 파일")
    parser.add_argument(
        "--holdout-extra", type=Path, action="append", default=[],
        help="겹침 검사에 더할 평가 파일(새 홀드아웃). 평가 세트와 같은 형식. 여러 번 줄 수 있다",
    )
    parser.add_argument("--eval-out", type=Path, help="laya-train --eval에 넣을 평가 세트 개발용 파일")
    parser.add_argument("--report", type=Path, help="겹침·비율 보고를 저장할 파일")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(Path(".env").resolve(), override=True)
    from app.ai.scripts.eval_retrieval import _git

    embed, save_cache, embedding_model = _cached_embed()
    decisions = load_reviewed(args.reviewed)
    started = time.perf_counter()
    result = asyncio.run(build(decisions, [EVAL_UTTERANCES, EVAL_SET, *args.holdout_extra], embed))
    save_cache()
    export, report = result["export"], result["report"]
    report["settings"] = {
        **_git(),
        "reviewed": args.reviewed.name,
        "embedding_model": embedding_model,
        "similar_cosine": SIMILAR_COSINE,
        "short_chars": SHORT_CHARS,
        "seconds": round(time.perf_counter() - started, 1),
        "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
    }

    args.out.write_text(to_jsonl(export), encoding="utf-8")
    if args.eval_out:
        args.eval_out.write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in eval_lines()), encoding="utf-8"
        )
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    overlap, balance = report["overlap"], report["balance"]
    print(f"판단 {report['decisions']} → 학습 줄 {balance['lines']} ({args.out})")
    print(f"겹쳐서 뺀 판단 {overlap['removed']} ({overlap['ratio']})", json.dumps(overlap["by_kind"]))
    for item in overlap["items"]:
        print(f"  {item['kind']:7} {item['decision_id']}  {item['text']}  ~ {item['eval_id']} {item.get('eval_text', '')}")
    if overlap["ratio"] and overlap["ratio"] > OVERLAP_ALERT:
        print(f"  겹친 비율이 {OVERLAP_ALERT:.0%}를 넘었다. 대본을 쓰는 방식을 점검한다")
    print("내보내지 않은 판단", json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report["export"].items()}))
    print(f"조회 비율 {balance['ratio']} (조회 {balance['lookup']} / {balance['lines']}, 목표 {LOOKUP_TARGET:.0%})")
    if balance["add_plain_to_target"]:
        print(f"  25%에 맞추려면 평범한 말(조회 아님) {balance['add_plain_to_target']}줄을 더 넣는다")
    if balance["add_lookup_to_target"]:
        print(f"  25%에 맞추려면 조회 줄 {balance['add_lookup_to_target']}줄을 더 넣는다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
