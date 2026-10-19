"""회의 판단 평가 문항이 형식에 맞고, 회의 순서대로 판단 요청이 만들어지는지 검증한다.

luna와 Laya가 같은 문항·같은 입력 글로 재야 학습 전후와 모델 간 비교가 된다.
"""

import json

from app.ai.features.meeting.context import build_judge_input
from app.ai.scripts.check_meeting_judge import EVAL_UTTERANCES, SETS, load_requests

ROWS = [
    json.loads(line)
    for line in EVAL_UTTERANCES.read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def test_rows_have_required_fields():
    for row in ROWS:
        assert row["set"] in SETS
        assert isinstance(row["needs_lookup"], bool)
        assert row["heard"].strip() and row["spoken"].strip()
        assert row["meeting"] and row["meeting_date"]
    assert len({row["id"] for row in ROWS}) == len(ROWS)


def test_each_meeting_is_contiguous():
    # 앞 발화를 순서대로 쌓으므로 한 회의의 발화가 떨어져 있으면 문맥이 끊긴다
    seen, previous = set(), None
    for row in ROWS:
        if row["meeting"] != previous:
            assert row["meeting"] not in seen
            seen.add(row["meeting"])
            previous = row["meeting"]


def test_requests_carry_earlier_utterances_of_same_meeting():
    requests = load_requests()
    assert len(requests) == len(ROWS)
    by_id = {row["id"]: request for row, request in requests}

    # q1 회의의 세 번째 발화는 앞 두 발화를 문맥으로 받는다
    third = by_id["q1-03"]
    assert [u.text for u in third.context] == [ROWS[0]["heard"], ROWS[1]["heard"]]
    assert "[방금 발화]\n" + ROWS[2]["heard"] in build_judge_input(third)

    # 회의가 바뀌면 문맥이 비어 있다
    first_of_set = {}
    for row, request in requests:
        first_of_set.setdefault(row["meeting"], request)
    assert all(request.context == () for request in first_of_set.values())


def test_sets_can_be_selected():
    vocative = load_requests(sets=("vocative",))
    assert vocative and all(row["set"] == "vocative" for row, _ in vocative)
