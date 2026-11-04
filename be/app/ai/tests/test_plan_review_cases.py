"""계획 수정 검토 평가 케이스(#177)가 현재 요청 계약과 어긋나지 않는지 확인한다. 모델은 부르지 않는다."""
import json
from pathlib import Path

import pytest

from app.ai import PlanEditReviewRequest

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "eval" / "plan_review_cases.json").read_text(encoding="utf-8")
)


def test_fixture_has_the_six_agreed_cases():
    assert [c["id"] for c in CASES] == [
        "survey_removed", "book_before_confirm", "fee_deadline_after_event",
        "ai_excluded_readded", "harmless_reorder", "undecided_dates",
    ]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_request_matches_contract(case):
    request = PlanEditReviewRequest.model_validate(case["request"])
    assert case["expect"]["outcome"] in {"issues", "no_issues", "any"}
    known = {s.code.value for s in request.included_steps} | {s.code.value for s in request.excluded_steps}
    expected = case["expect"]["must_mention_codes"] + case["expect"]["must_not_mention_codes"]
    assert set(expected) <= known
