"""운영 Action 본문 초안 평가 사례(#333)가 요청 계약과 맞는지, 자동 판정이 기준대로인지 본다. 모델은 부르지 않는다."""
import json
from pathlib import Path

import pytest

from app.ai import ActionDraftRequest
from app.ai.scripts.run_action_draft_eval import judge

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "eval" / "action_draft_cases.json").read_text(encoding="utf-8")
)
STEPS = ["DEMAND_SURVEY", "RECRUIT_NOTICE", "CHECK_RESPONSES", "COLLECT_FEES", "PRE_EVENT_NOTICE"]


def test_단계_5개마다_값이_모두_있는_사례와_미정_사례가_있다():
    requests = [ActionDraftRequest.model_validate(c["request"]) for c in CASES]
    assert [r.step.code.value for r in requests] == [code for code in STEPS for _ in range(2)]
    for full, missing in zip(requests[::2], requests[1::2]):
        assert full.event.location and full.event.end_date and full.step.deadline and full.action.due_date
        # 미정 사례: 장소·종료일·단계 기한·Action 기한이 비어 있다. 시작일은 운영 중이면 항상 있다.
        assert missing.event.location is None and missing.event.end_date is None
        assert missing.step.deadline is None and missing.action.due_date is None


def request(case_id):
    return ActionDraftRequest.model_validate(next(c for c in CASES if c["id"] == case_id)["request"])


def test_장소와_기한이_없으면_공지에_자리표시가_있어야_한다():
    req = request("survey_missing")
    assert judge(req, "📢 해맞이 산행 수요 조사\n장소: [장소 미정]\n응답 마감: [마감일]")["placeholder"] is True
    assert judge(req, "📢 해맞이 산행 수요 조사\n장소: [장소 미정]")["placeholder"] is False


def test_값이_모두_있거나_발송_메시지면_자리표시는_판정하지_않는다():
    assert judge(request("survey_full"), "📢 해커톤 수요 조사")["placeholder"] is None
    assert judge(request("fees_missing"), "[이름]님, 참가비 입금 부탁드려요.")["placeholder"] is None


@pytest.mark.parametrize("content, key", [
    ("📢 봄 MT 모집\n장소 예약을 확정됐습니다", "forbidden_absent"),
    ("[봄 MT 참가자 모집]\n신청 방법: [신청 링크]", "title_not_bracketed"),
    ("📢🌸 봄 MT 모집 🎉", "emoji_ok"),
])
def test_금지_표현_대괄호_제목_이모지_과다를_잡는다(content, key):
    assert judge(request("recruit_full"), content)[key] is False


def test_본문이_없으면_모두_실패로_둔다():
    assert not any(judge(request("recruit_full"), None).values())
