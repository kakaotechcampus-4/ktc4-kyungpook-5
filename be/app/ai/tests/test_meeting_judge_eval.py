"""회의 판단 평가 문항이 형식에 맞고, 회의 순서대로 판단 요청이 만들어지는지 검증한다.

luna와 Laya가 같은 문항·같은 입력 글로 재야 학습 전후와 모델 간 비교가 된다.
"""

import json

from app.ai.features.meeting.context import build_judge_input
from app.ai.scripts.check_meeting_judge import (
    EVAL_UTTERANCES,
    SETS,
    breakdown,
    confusion,
    load_requests,
)

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


def test_eval_set_rows_filter_by_split_and_carry_event(tmp_path):
    # 평가 세트는 회의 단위로 개발용·홀드아웃이 나뉘고, 회의에 묶인 행사가 판단 입력에 들어간다
    rows = [
        {"id": "a-01", "split": "dev", "meeting": "a", "meeting_date": "2026-03-05", "event": "2026 봄 MT",
         "heard": "숙소부터 정하죠", "needs_lookup": False},
        {"id": "a-02", "split": "dev", "meeting": "a", "meeting_date": "2026-03-05", "event": "2026 봄 MT",
         "heard": "작년엔 얼마였지", "needs_lookup": True},
        {"id": "b-01", "split": "holdout", "meeting": "b", "meeting_date": "2026-04-02", "event": None,
         "heard": "다음 안건 갈게요", "needs_lookup": False},
    ]
    path = tmp_path / "set.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    dev = load_requests(path, splits=("dev",))
    assert [row["id"] for row, _ in dev] == ["a-01", "a-02"]
    second = dev[1][1]
    assert [u.text for u in second.context] == ["숙소부터 정하죠"]
    assert "[행사]\n2026 봄 MT" in build_judge_input(second)

    both = load_requests(path, splits=("dev", "holdout"))
    holdout = both[-1][1]
    assert holdout.context == () and holdout.event is None


def test_confusion_counts_precision_and_false_alarms():
    records = (
        [{"truth": True, "pred": True}] * 3
        + [{"truth": True, "pred": False}]
        + [{"truth": False, "pred": True}] * 2
        + [{"truth": False, "pred": False}] * 8
    )
    result = confusion(records)
    assert result["recall"] == 0.75
    assert result["specificity"] == 0.8
    assert result["balanced_accuracy"] == 0.775
    assert result["precision"] == 0.6
    assert result["false_alarm_per_100"] == 20.0
    assert result["false_positive"] == "2 / 10" and result["missed"] == "1 / 4"


def test_confusion_has_no_precision_without_lookups():
    # 조회로 판단한 것이 없으면 정밀도를 0으로 적지 않는다. 낼 수 없는 값이다
    assert confusion([{"truth": True, "pred": False}, {"truth": False, "pred": False}])["precision"] is None


def test_breakdown_counts_wrong_by_bundle_and_tag():
    records = [
        {"truth": True, "pred": False, "bundle": "조회 필요", "category": ["지시어"]},
        {"truth": True, "pred": True, "bundle": "조회 필요", "category": ["지시어", "호칭"]},
        {"truth": False, "pred": True, "bundle": "언급만", "category": ["참고자료-제안"]},
        {"truth": False, "pred": False, "bundle": "언급만", "category": []},
    ]
    result = breakdown(records)
    assert result["by_bundle"] == {"언급만": {"items": 2, "wrong": 1}, "조회 필요": {"items": 2, "wrong": 1}}
    assert result["by_tag"]["지시어"] == {"items": 2, "wrong": 1}
    assert result["by_tag"]["참고자료-제안"] == {"items": 1, "wrong": 1}
