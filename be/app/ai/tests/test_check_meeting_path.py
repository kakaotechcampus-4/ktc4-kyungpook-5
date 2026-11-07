"""두 판단 경로의 지연 집계가 정답 묶음별로 맞게 세는지 검증한다(#245).

실제 모델은 부르지 않는다. 경로 기록을 직접 만들어 집계만 확인한다.
"""

from app.ai.scripts.check_meeting_path import group_of, summarize


def _record(group: str, luna_ms: int, jev_ms: int, query_ms: int | None = None) -> dict:
    jev = {"jev_ms": jev_ms, "lookup": query_ms is not None, "luna_calls": int(query_ms is not None)}
    if query_ms is not None:
        jev["query_ms"] = query_ms
    jev["ms"] = jev_ms + (query_ms or 0)
    return {"group": group, "luna": {"ms": luna_ms, "lookup": group == "lookup", "luna_calls": 1}, "jev": jev}


def test_group_of_puts_either_before_label():
    assert group_of({"needs_lookup": True}) == "lookup"
    assert group_of({"needs_lookup": False}) == "no_lookup"
    assert group_of({"needs_lookup": True, "either": True}) == "either"


def test_summary_counts_query_calls_only_where_jev_said_lookup():
    records = [
        _record("lookup", luna_ms=2000, jev_ms=500, query_ms=1800),  # Jev 경로 2.3초, 느림
        _record("no_lookup", luna_ms=2000, jev_ms=500),  # Jev 한 번으로 끝, 빠름
        _record("no_lookup", luna_ms=1900, jev_ms=600),
    ]
    summary = summarize(records)

    assert summary["all"]["pairs"] == 3
    assert summary["all"]["jev_faster"] == 2
    assert summary["all"]["luna_calls"] == {"luna": 3, "jev": 1}
    assert summary["lookup"]["jev"]["max_s"] == 2.3
    assert summary["lookup"]["query_only"]["n"] == 1
    assert summary["no_lookup"]["jev_with_query"] == 0
    assert "either" not in summary


def test_pair_with_error_is_left_out():
    # 한쪽이 실패한 발화는 같은 순간끼리 견줄 수 없어 빼고, 오류는 따로 센다
    failed = _record("lookup", luna_ms=2000, jev_ms=500)
    failed["luna"] = {"error": "TimeoutError: ", "ms": 10000}
    summary = summarize([failed, _record("no_lookup", luna_ms=2000, jev_ms=500)])
    assert summary["all"]["pairs"] == 1
    assert "lookup" not in summary
