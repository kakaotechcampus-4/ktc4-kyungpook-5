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
from collections import Counter
from collections.abc import Iterable
from typing import Self

from pydantic import Field, model_validator

from ...contracts import ContractModel, NonBlankStr
from .context import build_judge_input
from .questions import QUESTIONS_VERSION, RECORD_LOOKUP, judge_questions
from .schemas import JudgeReview, JudgeUtteranceRequest

# 둘 다 허용 표. label(RAG·NONE)과 같은 자리에서 센다
_EITHER = "EITHER"


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
    # 가장 많은 표가 둘로 갈려 정답을 정할 수 없다. 한 명 더 봐야 한다
    needs_review: tuple[str, ...] = ()
    # 둘 다 허용이 가장 많다. 채점하지 않는 말이라 학습에서 뺀다
    either: tuple[str, ...] = ()
    # 조회·아님·둘 다 허용이 같은 수로 갈렸다. 한 명 더 봐도 정해지기 어려워 뺀다
    three_way: tuple[str, ...] = ()
    # 검수 기록이 없다
    unreviewed: tuple[str, ...] = ()
    # 같은 입력이라 한 줄로 합친 판단 수
    merged: int = Field(default=0, ge=0)


def export_training_lines(decisions: Iterable[ReviewedDecision]) -> TrainingExport:
    """검수한 판단을 학습 파일 줄로 바꾼다.

    - 같은 사람이 같은 판단을 다시 검수하면 마지막 검수만 쓴다. 고치기 전 라벨을 세지 않는다
    - 입력 글(state)이 같은 판단은 한 줄로 합치고 검수도 합친다. 같은 줄이 두 번 들어가면
      그 판단만 두 배로 배우고, 학습과 평가에 같은 글이 섞이기 쉽다
    - 검수자 한 명이 표 하나를 낸다. either면 둘 다 허용, 아니면 label이다. 가장 많은 표로 정한다
    - 조회나 아님이 가장 많으면 expected를 넣고, 의견이 갈렸으면 조회·아님 표로만 gold 비율을 넣는다.
      둘 다 허용 표를 0.5씩 나눠 넣으면 고르지 않은 "0.5 / 0.5로 넣기"가 들어온다
    - 둘 다 허용이 가장 많으면 either로, 가장 많은 표가 둘이면 needs_review로,
      셋이 같은 수면 three_way로 돌려주고 내보내지 않는다
    """
    groups: dict[str, list[ReviewedDecision]] = {}
    for decision in decisions:
        groups.setdefault(build_judge_input(decision.request), []).append(decision)

    lines, needs_review, either, three_way, unreviewed, merged = [], [], [], [], [], 0
    for state, group in groups.items():
        merged += len(group) - 1
        ids = [decision.decision_id for decision in group]
        votes = Counter(
            _EITHER if review.either else review.label
            for decision in group
            for review in _latest_by_reviewer(decision.reviews)
        )
        if not votes:
            unreviewed.extend(ids)
            continue
        most = max(votes.values())
        winners = [vote for vote, count in votes.items() if count == most]
        if len(winners) == 3:
            three_way.extend(ids)
            continue
        if len(winners) == 2:
            needs_review.extend(ids)
            continue
        if winners == [_EITHER]:
            either.extend(ids)
            continue

        line = {
            "state": state,
            "questions": judge_questions(),
            "expected": {RECORD_LOOKUP: winners == ["RAG"]},
        }
        lookups, others = votes["RAG"], votes["NONE"]
        if lookups and others:
            line["gold"] = {
                RECORD_LOOKUP: {
                    "probabilities": {
                        "false": round(others / (lookups + others), 4),
                        "true": round(lookups / (lookups + others), 4),
                    }
                }
            }
        lines.append(line)

    return TrainingExport(
        questions_version=QUESTIONS_VERSION,
        lines=tuple(lines),
        needs_review=tuple(needs_review),
        either=tuple(either),
        three_way=tuple(three_way),
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
