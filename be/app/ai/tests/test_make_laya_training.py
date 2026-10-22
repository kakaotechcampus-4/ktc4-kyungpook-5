"""학습 파일을 만드는 스크립트가 평가 문항과 겹치는 판단을 빼고 조회 비율을 알려 주는지 확인한다(#117).

임베딩은 키 없이 돌도록 가짜로 넣는다. 실제 임베딩으로 정한 기준(0.85)은 architecture.md 6단계에 있다.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from app.ai.features.meeting.schemas import JudgeReview, JudgeUtteranceRequest, MeetingUtterance
from app.ai.features.meeting.training import ReviewedDecision
from app.ai.scripts.check_meeting_judge import EVAL_SET, EVAL_UTTERANCES, load_requests
from app.ai.scripts.make_laya_training import (
    build,
    eval_lines,
    eval_sentences,
    lookup_balance,
    normalize,
)

KST = timezone(timedelta(hours=9))
SPOKEN = datetime(2026, 11, 2, 14, 0, tzinfo=KST)
EVAL_PATHS = [EVAL_UTTERANCES, EVAL_SET]
SET_ROWS = [json.loads(line) for line in EVAL_SET.read_text(encoding="utf-8").splitlines() if line.strip()]
# 평가 세트에 있는 긴 조회 질문. 이 문장과 뜻이 같은 학습 문장을 가짜 임베딩으로 만든다
EVAL_QUESTION = next(r["heard"] for r in SET_ROWS if r["needs_lookup"] and len(normalize(r["heard"])) > 15)
NEAR = "학습 대본에서 거의 같은 뜻으로 쓴 질문"


def _decision(decision_id, text, label="RAG", request=None):
    request = request or JudgeUtteranceRequest(
        meeting_id="mtg_train",
        club_id="clb_1",
        utterance=MeetingUtterance(utterance_id=decision_id, seq=1, text=text, started_at=SPOKEN, ended_at=SPOKEN),
    )
    review = JudgeReview(
        decision_id=decision_id,
        label=label,
        reason_code="MONOLOGUE" if label == "NONE" else None,
        reviewer="reviewer-1",
        blind=True,
        reviewed_at=SPOKEN,
    )
    return ReviewedDecision(decision_id=decision_id, request=request, reviews=(review,))


async def _embed(texts):
    """평가 질문과 NEAR는 거의 같은 방향, 나머지 평가 문장과 학습 문장은 서로 직각이다"""
    eval_texts = {text for _, text in eval_sentences(EVAL_PATHS)}

    def vector(text):
        if text == EVAL_QUESTION:
            return (0.0, 0.0, 1.0)
        if text == NEAR:
            return (0.0, 0.1, 1.0)
        return (1.0, 0.0, 0.0) if text in eval_texts else (0.0, 1.0, 0.0)

    return [vector(text) for text in texts]


def _build(decisions):
    return asyncio.run(build(decisions, EVAL_PATHS, _embed))


def test_글자는_공백과_문장부호를_빼고_견준다():
    assert normalize("작년 회비, 얼마였지?") == normalize("작년회비 얼마였지") == "작년회비얼마였지"


def test_평가_쪽은_대본과_판단_입력_글을_모두_쓴다():
    # 학습 대본은 음성을 거치지 않은 글일 수 있어 대본과도 견준다
    row = next(r for r in SET_ROWS if r["spoken"] != r["heard"])
    texts = {text for _, text in eval_sentences([EVAL_SET])}
    assert {row["spoken"], row["heard"]} <= texts


def test_평가_문장과_글자가_같으면_뺀다():
    result = _build([_decision("d-1", EVAL_QUESTION.replace("?", "") + "  "), _decision("d-2", "작년 동아리 티셔츠 단가 얼마였지?")])

    [overlap] = result["report"]["overlap"]["items"]
    assert (overlap["decision_id"], overlap["kind"]) == ("d-1", "same")
    assert len(result["export"].lines) == 1


def test_임베딩이_가까우면_글자가_달라도_뺀다():
    result = _build([_decision("d-1", NEAR)])

    [overlap] = result["report"]["overlap"]["items"]
    assert overlap["kind"] == "similar" and overlap["eval_text"] == EVAL_QUESTION
    assert overlap["cosine"] >= 0.85
    assert result["export"].lines == ()


def test_짧은_말은_평가_문장과_같아도_넣는다():
    # 맞장구·진행 말은 어느 회의에나 나온다. 빼면 평범한 말이 줄어든다(4단계)
    short = next(r["heard"] for r in SET_ROWS if len(normalize(r["heard"])) <= 6)

    result = _build([_decision("d-1", short, label="NONE")])

    assert result["report"]["overlap"]["removed"] == 0
    assert len(result["export"].lines) == 1


def test_입력_글_전체가_같으면_짧은_말이어도_뺀다():
    # 앞 발화와 회의 날짜까지 같으면 Laya는 입력 글을 외워 맞힐 수 있다. 홀드아웃도 본다
    row, request = next(
        (row, request)
        for row, request in load_requests(EVAL_SET)
        if row["split"] == "holdout" and len(normalize(row["heard"])) <= 6
    )

    result = _build([_decision("d-1", row["heard"], label="NONE", request=request)])

    [overlap] = result["report"]["overlap"]["items"]
    assert (overlap["kind"], overlap["eval_id"]) == ("state", row["id"])


def test_겹친_비율과_종류를_보고에_남긴다():
    result = _build([_decision("d-1", NEAR), _decision("d-2", "작년 동아리 티셔츠 단가 얼마였지?")])

    overlap = result["report"]["overlap"]
    assert (overlap["removed"], overlap["ratio"]) == (1, 0.5)
    assert overlap["by_kind"] == {"state": 0, "same": 0, "similar": 1}


def test_조회_비율이_높으면_더_넣을_평범한_말_수를_알려_준다():
    lines = [{"expected": {"record_lookup": value}} for value in (True, True, False, False)]

    balance = lookup_balance(lines)

    # 조회 2줄이 25%가 되려면 전체 8줄. 평범한 말 4줄을 더 넣는다
    assert (balance["ratio"], balance["add_plain_to_target"], balance["add_lookup_to_target"]) == (0.5, 4, 0)


def test_조회_비율이_낮으면_더_넣을_조회_줄_수를_알려_준다():
    lines = [{"expected": {"record_lookup": i == 0}} for i in range(10)]

    balance = lookup_balance(lines)

    # (1 + x) / (10 + x) = 25% 이면 x = 2
    assert (balance["ratio"], balance["add_plain_to_target"], balance["add_lookup_to_target"]) == (0.1, 0, 2)


def test_laya_train_평가_파일에는_개발용만_넣는다():
    # --eval은 학습 전후 점수를 낸다. 홀드아웃을 넣으면 학습할 때마다 홀드아웃을 보게 된다
    lines = eval_lines()

    dev_scored = [r for r in SET_ROWS if r["split"] == "dev" and not r.get("either")]
    holdout = {r["heard"] for r in SET_ROWS if r["split"] == "holdout"}
    assert len(lines) == len(dev_scored)
    assert not any(line["state"].endswith(text) for line in lines for text in holdout if len(text) > 10)
