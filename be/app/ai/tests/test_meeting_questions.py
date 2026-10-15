"""판단 전용 모델에 던질 판단 질문이 학습과 판단에서 같게 유지되는지 확인한다(#117)."""

import hashlib
import json

from app.ai.features.meeting.questions import (
    QUESTIONS_VERSION,
    RECORD_LOOKUP,
    judge_questions,
)

# 질문 문구를 바꾸면 이 값이 달라져 테스트가 실패한다.
# 바꿀 때는 QUESTIONS_VERSION을 올리고, 새 버전과 해시를 여기에 더한다
QUESTIONS_SHA256 = {
    "meeting-questions-v1": "bd2950cc1b2a25429fd7f6a8812979fd5a4ca4958c669ac577976a222f8d37c0",
}


def test_질문_문구를_바꾸면_버전도_올린다():
    text = json.dumps(judge_questions(), ensure_ascii=False, sort_keys=True)

    assert QUESTIONS_SHA256.get(QUESTIONS_VERSION) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_기록_조회는_예_아니오_질문이다():
    question = judge_questions()[RECORD_LOOKUP]

    assert question["type"] == "noul"
    assert question["instructions"].strip()


def test_예_아니오_질문은_양쪽_설명을_모두_적는다():
    # 비우면 영어 기본 문구가 한국어 입력 사이에 들어간다
    for question in judge_questions().values():
        if question["type"] == "noul":
            assert set(question["criteria"]) == {"false", "true"}
            assert all(text.strip() for text in question["criteria"].values())


def test_받은_질문을_고쳐도_원본은_그대로다():
    questions = judge_questions()
    questions[RECORD_LOOKUP]["instructions"] = "바뀐 질문"

    assert judge_questions()[RECORD_LOOKUP]["instructions"] != "바뀐 질문"
