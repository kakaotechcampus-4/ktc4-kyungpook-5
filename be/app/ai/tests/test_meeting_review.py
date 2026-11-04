"""회의 판단 검수 기록이 학습 데이터의 정답으로 쓸 수 있는 값만 받는지 확인한다(#117)."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.ai.features.meeting.schemas import JudgeReview

KST = timezone(timedelta(hours=9))
AT = datetime(2026, 10, 20, 10, 0, tzinfo=KST)


def _review(**fields):
    values = {
        "decision_id": "cd-31",
        "label": "NONE",
        "reason_code": "CURRENT_STATUS",
        "reviewer": "reviewer-1",
        "blind": True,
        "reviewed_at": AT,
    }
    return JudgeReview(**(values | fields))


def test_NONE은_조회하지_않은_이유와_함께_받는다():
    review = _review()

    assert (review.label, review.reason_code, review.schema_version) == ("NONE", "CURRENT_STATUS", 2)


def test_둘_다_허용도_더_가까운_쪽_라벨과_함께_받는다():
    # 평가 세트와 같은 방식이다. 학습 파일 만드는 방식을 바꿔도 다시 검수하지 않게 둔다
    review = _review(reason_code="REFERENCE_MATERIAL", either=True)

    assert (review.label, review.either) == ("NONE", True)


def test_AI에게_시킨_말인지는_묻지_않았으면_비워_둔다():
    # False는 시킨 말이 아니라고 확인한 것이다
    assert _review().direct_request is None
    assert _review(direct_request=False).direct_request is False


def test_RAG는_이유_없이_받는다():
    review = _review(label="RAG", reason_code=None)

    assert review.reason_code is None


@pytest.mark.parametrize(
    "fields",
    [
        {"label": "NONE", "reason_code": None},
        {"label": "RAG", "reason_code": "CHITCHAT"},
    ],
)
def test_이유는_NONE에만_있다(fields):
    with pytest.raises(ValidationError):
        _review(**fields)


def test_정해진_이유_코드만_받는다():
    # ASK_PERSON은 CURRENT_STATUS로 바뀌었다. 사람을 불렀는지는 기준이 아니다
    with pytest.raises(ValidationError):
        _review(reason_code="ASK_PERSON")


def test_시간대_없는_검수_시각은_받지_않는다():
    with pytest.raises(ValidationError):
        _review(reviewed_at=AT.replace(tzinfo=None))


def test_버전_1_기록은_버전_2로_읽는다():
    # 버전 1에는 둘 다 허용 칸이 없었고, AI에게 시킨 말인지는 묻지 않았다
    v1 = (
        '{"decision_id": "cd-31", "label": "NONE", "reason_code": "REFERENCE_MATERIAL", "reviewer": "reviewer-1",'
        ' "blind": true, "reviewed_at": "2026-10-20T10:00:00+09:00", "schema_version": 1}'
    )

    review = JudgeReview.model_validate_json(v1)

    assert (review.schema_version, review.label, review.either, review.direct_request) == (2, "NONE", False, None)


def test_버전_1에_새_칸이_있으면_받지_않는다():
    with pytest.raises(ValidationError):
        _review(schema_version=1, either=True)


def test_모르는_형식_버전은_받지_않는다():
    with pytest.raises(ValidationError):
        _review(schema_version=3)


def test_JSON으로_저장했다가_그대로_다시_읽는다():
    review = _review()

    assert JudgeReview.model_validate_json(review.model_dump_json()) == review
