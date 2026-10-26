"""판단 전용 모델(Laya)에 던질 판단 질문을 정의한다(#117).

luna는 prompts/judge.md 지시문으로 판단하고, Laya는 입력과 함께 이 짧은 질문과
양쪽 설명을 읽고 판단한다. 학습할 때와 판단할 때 같은 문구여야 학습한 판단이 나오므로
문구를 한 곳에 두고 버전을 붙인다.

설명 문구도 판단 기준이다. 문구만 바꿔도 P(true)가 움직인다(Laya examples/09).
그래서 양쪽을 같은 무게로 쓰고, 설명을 비우지 않는다. 비우면 영어 기본 문구
("no, the statement does not hold")가 한국어 입력 사이에 들어간다.

질문 형식은 Laya 요청의 questions 항목과 같다.
"""

from copy import deepcopy

# 아래 문구를 바꾸면 올린다. 바꾸기 전에 모은 학습 데이터와 섞지 않기 위해서다
QUESTIONS_VERSION = "meeting-questions-v1"

RECORD_LOOKUP = "record_lookup"

# 기준은 prompts/judge.md(v5)와 같다. 조회가 필요한 경우와 필요 없는 경우를 줄여 옮겼다
_QUESTIONS = {
    RECORD_LOOKUP: {
        "type": "noul",
        "instructions": (
            "방금 발화에 동아리의 과거 기록(회칙·장부·행사 보고서)을 찾아봐야 답할 수 있는 "
            "과거 금액·인원·일정·규정 질문이 있나요? 사람을 불러 물어도 같습니다. "
            "지금 진행 상황을 묻는 말, 혼잣말, 잡담, 앞으로 할 일을 정하는 말, "
            "과거 자료를 같이 보자는 말은 해당하지 않습니다."
        ),
        "criteria": {
            "false": "기록을 찾아봐야 답할 질문이 없음",
            "true": "기록을 찾아봐야 답할 질문이 있음",
        },
    },
}


def judge_questions() -> dict:
    """Laya 요청과 학습 파일에 넣을 판단 질문. 호출한 쪽이 고쳐도 원본은 그대로다"""
    return deepcopy(_QUESTIONS)
