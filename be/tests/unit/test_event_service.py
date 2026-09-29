"""DB 없이 도는 행사 서비스 테스트."""

from datetime import UTC, datetime

from app.services.event_service import default_title


def test_default_title_uses_korean_date() -> None:
    # UTC 3월 1일 16시 = KST 3월 2일 01시
    assert default_title(datetime(2026, 3, 1, 16, 0, tzinfo=UTC)) == "새 행사 · 3월 2일"


def test_default_title_before_kst_midnight() -> None:
    assert default_title(datetime(2026, 3, 1, 14, 59, tzinfo=UTC)) == "새 행사 · 3월 1일"
