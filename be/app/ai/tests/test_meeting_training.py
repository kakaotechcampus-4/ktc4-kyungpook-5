"""검수한 회의 판단을 Laya 학습 파일 줄로 바꾸는지 확인한다(#117)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.ai.features.meeting.context import build_judge_input
from app.ai.features.meeting.questions import QUESTIONS_VERSION, judge_questions
from app.ai.features.meeting.schemas import JudgeReview, JudgeUtteranceRequest, MeetingUtterance
from app.ai.features.meeting.training import ReviewedDecision, export_training_lines, to_jsonl

KST = timezone(timedelta(hours=9))
SPOKEN = datetime(2026, 3, 5, 14, 0, tzinfo=KST)
REVIEWED = datetime(2026, 10, 20, 10, 0, tzinfo=KST)


def _request(text="민수야, 작년 회칙상 환불 기준이 뭐였지?", context=()):
    seq = len(context) + 1
    return JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id="clb_1",
        utterance=MeetingUtterance(
            utterance_id=f"u-{seq}", seq=seq, text=text, started_at=SPOKEN, ended_at=SPOKEN
        ),
        context=tuple(
            MeetingUtterance(utterance_id=f"u-{i}", seq=i, text=t, started_at=SPOKEN, ended_at=SPOKEN)
            for i, t in enumerate(context, start=1)
        ),
    )


def _review(decision_id, label, reviewer="reviewer-1", minutes=0):
    return JudgeReview(
        decision_id=decision_id,
        label=label,
        reason_code="CURRENT_STATUS" if label == "NONE" else None,
        reviewer=reviewer,
        blind=True,
        reviewed_at=REVIEWED + timedelta(minutes=minutes),
    )


def _decision(decision_id, *labels, request=None):
    reviews = tuple(
        _review(decision_id, label, reviewer=f"reviewer-{i}") for i, label in enumerate(labels, start=1)
    )
    return ReviewedDecision(decision_id=decision_id, request=request or _request(), reviews=reviews)


def test_한_명이_검수하면_정답_하나만_넣는다():
    request = _request()

    export = export_training_lines([_decision("cd-1", "RAG", request=request)])

    [line] = export.lines
    assert line == {
        "state": build_judge_input(request),
        "questions": judge_questions(),
        "expected": {"record_lookup": True},
    }
    assert export.questions_version == QUESTIONS_VERSION


def test_입력은_그때_luna가_본_글_그대로다():
    # 앞 발화와 회의 날짜까지 같아야 학습한 판단이 실제 판단과 같은 입력을 본다
    request = _request("그때 숙소비 얼마였지?", context=("작년 봄 MT 얘기인데",))

    [line] = export_training_lines([_decision("cd-1", "RAG", request=request)]).lines

    assert line["state"] == build_judge_input(request)
    assert "작년 봄 MT 얘기인데" in line["state"]
    assert "2026-03-05" in line["state"]


def test_의견이_갈리면_다수를_정답으로_하고_비율도_넣는다():
    [line] = export_training_lines([_decision("cd-1", "NONE", "NONE", "RAG")]).lines

    assert line["expected"] == {"record_lookup": False}
    assert line["gold"] == {"record_lookup": {"probabilities": {"false": 0.6667, "true": 0.3333}}}


def test_여러_명이_모두_같으면_비율을_넣지_않는다():
    [line] = export_training_lines([_decision("cd-1", "RAG", "RAG")]).lines

    assert "gold" not in line


def test_반반으로_갈리면_내보내지_않고_한_명_더_보게_한다():
    export = export_training_lines(
        [_decision("cd-1", "RAG", "NONE"), _decision("cd-2", "RAG", request=_request("작년 회비 얼마였지?"))]
    )

    assert export.needs_review == ("cd-1",)
    assert len(export.lines) == 1


def test_검수하지_않은_판단은_내보내지_않는다():
    # luna의 판단은 정답 후보일 뿐이다
    export = export_training_lines([_decision("cd-1")])

    assert export.lines == ()
    assert export.unreviewed == ("cd-1",)


def test_같은_사람이_다시_검수하면_마지막_검수만_쓴다():
    # AI가 다시 보라고 짚어 사람이 고친 경우. 고치기 전 라벨을 표로 세지 않는다
    reviews = (
        _review("cd-1", "NONE", minutes=0),
        _review("cd-1", "RAG", minutes=5),
    )
    decision = ReviewedDecision(decision_id="cd-1", request=_request(), reviews=reviews)

    [line] = export_training_lines([decision]).lines

    assert line["expected"] == {"record_lookup": True}
    assert "gold" not in line


def test_같은_입력은_한_줄로_합치고_검수도_합친다():
    # 같은 질문을 다시 하면(AI-MEET-04) 같은 입력이 두 번 생길 수 있다
    request = _request()
    first = _decision("cd-1", "RAG", request=request)
    second = ReviewedDecision(
        decision_id="cd-2", request=request, reviews=(_review("cd-2", "RAG", reviewer="reviewer-9"),)
    )

    export = export_training_lines([first, second])

    assert len(export.lines) == 1
    assert export.merged == 1


def test_다른_판단의_검수는_받지_않는다():
    with pytest.raises(ValidationError):
        ReviewedDecision(decision_id="cd-1", request=_request(), reviews=(_review("cd-2", "RAG"),))


def test_JSONL은_한_줄에_판단_하나이고_한글을_그대로_둔다():
    export = export_training_lines(
        [_decision("cd-1", "RAG"), _decision("cd-2", "NONE", request=_request("점심 뭐 먹지?"))]
    )

    text = to_jsonl(export)

    rows = [json.loads(line) for line in text.splitlines()]
    assert [row["expected"]["record_lookup"] for row in rows] == [True, False]
    assert "점심 뭐 먹지?" in text
