"""계획 수정 후 검토: 결과 계약, 입력에 없는 단계 코드 거부, 메시지 분리. 실제 모델은 부르지 않는다."""
import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

from app.ai import (
    AIInvalidResponseError, AIRetryableError, PlanChangeSet, PlanEditReviewRequest,
    PlanEditReviewResult, PlanReviewItem, ReviewExcludedStep, ReviewStep, review_plan_edit,
)
from app.ai.contracts import ConditionMeta, MessageEvidence, PlanningConditions, PlanningDraft
from app.ai.features.planning.review import review as review_module
from app.core.enums import EventType, StepActor, StepCode, StepPhase


def item(step_codes=(StepCode.BOOK_VENUE,)):
    return PlanReviewItem(step_codes=step_codes, kind="order", message="예약이 인원 확정보다 앞서요.")


def no_issues():
    return PlanEditReviewResult(outcome="no_issues", items=())


def step(code):
    return ReviewStep(code=code, name=code.value, phase=StepPhase.RECRUITING, actor=StepActor.MANUAL)


def request():
    draft = PlanningDraft(
        conditions=PlanningConditions(event_type=EventType.MT, headcount=20),
        condition_meta={"headcount": ConditionMeta(
            status="tentative", evidence=MessageEvidence(message_id="m1", quote="대략 20명"))},
    )
    return PlanEditReviewRequest(
        draft=draft, today=date(2026, 11, 1),
        included_steps=tuple(step(c) for c in (
            StepCode.RECRUIT_NOTICE, StepCode.BOOK_VENUE, StepCode.CONFIRM_DETAILS, StepCode.COLLECT_FEES)),
        excluded_steps=(ReviewExcludedStep(
            code=StepCode.DEMAND_SURVEY, name="수요 조사", excluded_by="user"),),
        changes=PlanChangeSet(removed_codes=(StepCode.DEMAND_SURVEY,), moved_codes=(StepCode.BOOK_VENUE,)),
    )


def fake(monkeypatch, result):
    seen = {}

    async def _fake(messages, schema):
        seen["messages"] = messages
        seen["schema"] = schema
        return result

    monkeypatch.setattr(review_module, "ainvoke_structured", _fake)
    return seen


def fake_raises(monkeypatch, error):
    async def _fake(messages, schema):
        raise error

    monkeypatch.setattr(review_module, "ainvoke_structured", _fake)


def test_결과_개수와_outcome이_맞아야_한다():
    with pytest.raises(ValidationError):
        PlanEditReviewResult(outcome="issues", items=())
    with pytest.raises(ValidationError):
        PlanEditReviewResult(outcome="no_issues", items=(item(),))
    with pytest.raises(ValidationError):
        PlanEditReviewResult(outcome="issues", items=(item(),) * 5)


def test_입력에_없는_코드는_거부한다(monkeypatch):
    fake(monkeypatch, PlanEditReviewResult(
        outcome="issues", items=(item(step_codes=(StepCode.REFUND_FEES,)),)))
    with pytest.raises(AIInvalidResponseError):
        asyncio.run(review_plan_edit(request()))


def test_빠진_단계_코드는_허용한다(monkeypatch):
    fake(monkeypatch, PlanEditReviewResult(
        outcome="issues", items=(item(step_codes=(StepCode.DEMAND_SURVEY,)),)))
    assert asyncio.run(review_plan_edit(request())).items[0].step_codes == (StepCode.DEMAND_SURVEY,)


def test_요청_데이터는_시스템_지시와_분리된_사용자_메시지로_간다(monkeypatch):
    seen = fake(monkeypatch, no_issues())
    req = request()
    asyncio.run(review_plan_edit(req))
    system, human = seen["messages"]
    assert system.content == review_module._PROMPT
    assert human.content == req.model_dump_json()
    assert seen["schema"] is PlanEditReviewResult


def test_모델_오류는_AI_오류로_올라간다(monkeypatch):
    fake_raises(monkeypatch, AIRetryableError("x"))
    with pytest.raises(AIRetryableError):
        asyncio.run(review_plan_edit(request()))
