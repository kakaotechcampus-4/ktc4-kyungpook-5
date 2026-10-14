"""검수한 회의 판단을 판단 전용 모델(Laya)의 학습 파일 줄로 바꾼다(#117).

한 줄은 Laya JSONL 형식이다.

    {"state": 그때 luna가 본 입력 글,
     "questions": 판단 질문(questions.py),
     "expected": {"record_lookup": true},
     "gold": {"record_lookup": {"probabilities": {"false": 0.33, "true": 0.67}}}}  ← 의견이 갈렸을 때만

정답은 사람이 붙인 검수 기록에서만 만든다. luna의 판단은 정답 후보일 뿐이라 쓰지 않는다.
저장 위치는 정하지 않았으므로 줄만 만들고, 파일로 쓰는 일은 부르는 쪽이 한다.
"""

import json
from collections.abc import Iterable
from typing import Self

from pydantic import Field, model_validator

from ...contracts import ContractModel, NonBlankStr
from .context import build_judge_input
from .questions import QUESTIONS_VERSION, RECORD_LOOKUP, judge_questions
from .schemas import JudgeReview, JudgeUtteranceRequest


class ReviewedDecision(ContractModel):
    """판단 기록 하나와 그 판단에 붙은 검수 기록들"""

    decision_id: NonBlankStr
    # 그때 판단에 넘긴 요청. BE가 판단 기록의 발화 id와 버전으로 다시 만든다.
    # 나중에 고쳐진 전사로 만들면 그때 모델이 본 입력과 달라진다
    request: JudgeUtteranceRequest
    reviews: tuple[JudgeReview, ...] = ()

    @model_validator(mode="after")
    def _reviews_belong_here(self) -> Self:
        if any(review.decision_id != self.decision_id for review in self.reviews):
            raise ValueError("다른 판단 기록의 검수가 섞여 있습니다")
        return self


class TrainingExport(ContractModel):
    """학습 파일로 내보낸 결과"""

    # 질문 문구 버전. 버전이 다른 줄을 한 파일에 섞지 않는다
    questions_version: str
    lines: tuple[dict, ...] = ()
    # 검수자 의견이 반반으로 갈려 정답을 정할 수 없다. 한 명 더 봐야 한다
    needs_review: tuple[str, ...] = ()
    # 검수 기록이 없다
    unreviewed: tuple[str, ...] = ()
    # 같은 입력이라 한 줄로 합친 판단 수
    merged: int = Field(default=0, ge=0)


def export_training_lines(decisions: Iterable[ReviewedDecision]) -> TrainingExport:
    """검수한 판단을 학습 파일 줄로 바꾼다.

    - 같은 사람이 같은 판단을 다시 검수하면 마지막 검수만 쓴다. 고치기 전 라벨을 세지 않는다
    - 입력 글(state)이 같은 판단은 한 줄로 합치고 검수도 합친다. 같은 줄이 두 번 들어가면
      그 판단만 두 배로 배우고, 학습과 평가에 같은 글이 섞이기 쉽다
    - 한 명이 검수했거나 모두 같은 라벨이면 expected만, 의견이 갈렸으면 gold 비율도 넣는다
    - 반반으로 갈리면 내보내지 않고 needs_review로 돌려준다
    """
    groups: dict[str, list[ReviewedDecision]] = {}
    for decision in decisions:
        groups.setdefault(build_judge_input(decision.request), []).append(decision)

    lines, needs_review, unreviewed, merged = [], [], [], 0
    for state, group in groups.items():
        merged += len(group) - 1
        ids = [decision.decision_id for decision in group]
        labels = [review.label for decision in group for review in _latest_by_reviewer(decision.reviews)]
        if not labels:
            unreviewed.extend(ids)
            continue
        lookups = labels.count("RAG")
        if lookups * 2 == len(labels):
            needs_review.extend(ids)
            continue

        line = {
            "state": state,
            "questions": judge_questions(),
            "expected": {RECORD_LOOKUP: lookups * 2 > len(labels)},
        }
        if 0 < lookups < len(labels):
            line["gold"] = {
                RECORD_LOOKUP: {
                    "probabilities": {
                        "false": round((len(labels) - lookups) / len(labels), 4),
                        "true": round(lookups / len(labels), 4),
                    }
                }
            }
        lines.append(line)

    return TrainingExport(
        questions_version=QUESTIONS_VERSION,
        lines=tuple(lines),
        needs_review=tuple(needs_review),
        unreviewed=tuple(unreviewed),
        merged=merged,
    )


def to_jsonl(export: TrainingExport) -> str:
    """laya-train --data에 넣을 JSONL 글. 한글을 그대로 둔다"""
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in export.lines)


def _latest_by_reviewer(reviews: tuple[JudgeReview, ...]) -> list[JudgeReview]:
    latest: dict[str, JudgeReview] = {}
    for review in reviews:
        kept = latest.get(review.reviewer)
        if kept is None or review.reviewed_at > kept.reviewed_at:
            latest[review.reviewer] = review
    return list(latest.values())
