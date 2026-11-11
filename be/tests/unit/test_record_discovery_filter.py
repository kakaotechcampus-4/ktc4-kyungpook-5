"""자료함 검색의 AI 추천 거르기 규칙 (테스트 브랜치, 자료함 경로 전용)."""

from app.services.record_discovery_service import select_semantic_records


def test_1등_점수가_바닥선보다_낮으면_AI_추천이_없다() -> None:
    # 관계없는 검색어(예: '양자역학 블랙홀')는 1등도 0.2 안팎이다.
    assert select_semantic_records({"a": 0.18, "b": 0.12}) == set()


def test_1등과_가까운_자료만_남는다() -> None:
    # 기본 범위 0.1: 1등 0.53 - 0.1 = 0.43 이상만 남는다.
    scores = {"a": 0.53, "b": 0.48, "c": 0.42, "d": 0.29}
    assert select_semantic_records(scores) == {"a", "b"}


def test_자료는_최대_5개까지만_남는다() -> None:
    scores = {f"r{i}": 0.50 - i * 0.01 for i in range(8)}
    assert select_semantic_records(scores) == {"r0", "r1", "r2", "r3", "r4"}


def test_기준값을_인자로_바꿀_수_있다() -> None:
    scores = {"a": 0.30, "b": 0.27, "c": 0.14}
    assert select_semantic_records(scores, min_top=0.2, window=0.05, max_records=10) == {"a", "b"}
    assert select_semantic_records(scores, min_top=0.35) == set()


def test_점수가_없으면_빈_집합이다() -> None:
    assert select_semantic_records({}) == set()
