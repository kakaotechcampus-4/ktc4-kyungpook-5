"""실제 두 Node를 실행하되 구성 모델만 대체해 잘못된 계획이 채택되지 않게 한다."""

import asyncio
import json
from functools import partial

import pytest

from app.ai.contracts import RecordSource, SourceLocation
from app.ai.errors import AIConfigError, AITimeoutError
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.generation.catalog import CATALOG
from app.ai.features.planning.generation.entrypoints import ButtonPlanGenerationRequest, run_button_plan_generation
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.generation.schemas import (
    ButtonGenerationTrigger, PlanComposition, PlanGenerationInput, PlanGenerationResult, PlanningGenerationState,
)
from app.ai.features.planning.schemas import PlanningConditions
from app.ai.features.retrieval.schemas import RecordFact


def composition(steps=None, **changes):
    steps=steps or [dict(code="RESEARCH_VENUE",purpose="규모에 맞는 후보와 견적 확인"),
                    dict(code="EVENT_DAY",purpose="집결·인원 확인")]
    included={s["code"] for s in steps}
    data=dict(steps=steps,excluded_steps=[dict(code=x.code,reason="이번 초안에서 제외") for x in CATALOG if x.code not in included])
    data.update(changes)
    return PlanComposition.model_validate(data)


def request(**changes):
    data=dict(basis_draft=PlanningDraft(conditions=PlanningConditions(event_type="MT",headcount=50,fee_per_person=25000)),
              trigger=ButtonGenerationTrigger(request_id="click-1"),reference_date="2026-10-24")
    data.update(changes)
    return PlanGenerationInput(**data)


class Model:
    def __init__(self, answer=None):
        self.answer=answer or composition()
        self.calls=[]

    async def __call__(self, messages, schema):
        self.calls.append((messages,schema))
        if isinstance(self.answer,Exception): raise self.answer
        return self.answer


def test_generation_uses_catalog_and_keeps_unknown_dates_and_original_draft():
    req=request()
    before=req.model_dump_json()
    model=Model()
    result=asyncio.run(run_plan_generation(req,invoke=model))
    assert result.status=="generated" and result.model_calls==1
    preview=result.preview
    assert preview.basis_draft==req.basis_draft
    assert preview.steps[0].name=="장소·교통 알아보기" and preview.steps[0].actor=="MANUAL"
    assert all(s.starts_at is None and s.deadline is None for s in preview.steps)
    assert "행사 날짜" in preview.open_questions
    assert req.model_dump_json()==before
    data=json.loads(model.calls[0][0][1].content)
    assert len(data["catalog"])==13 and data["basis_draft"]["conditions"]["start_date"] is None


@pytest.mark.parametrize("change",[
    {"steps":[dict(code="RESEARCH_VENUE",purpose="장소",starts_at="2026-11-01T09:00:00+09:00")]},
    {"steps":[dict(code="RESEARCH_VENUE",purpose="장소",actions=[dict(type="NOTICE",title="불허 행동")])]},
    {"steps":[dict(code="EVENT_DAY",purpose="당일"),dict(code="RESEARCH_VENUE",purpose="역순")]},
    {"steps":[dict(code="EVENT_DAY",purpose="당일"),dict(code="EVENT_DAY",purpose="중복")]},
    {"excluded_steps":[]},
    {"assumptions":[dict(content="지어낸 기록",fact_ids=["f999"])]},
    {"steps":[dict(code="CANCEL_RECORD",purpose="취소 단계 혼입")]},
])
def test_invalid_compositions_return_safe_failure(change):
    model=Model(composition(**change))
    result=asyncio.run(run_plan_generation(request(),invoke=model))
    assert result.status=="failed" and result.preview is None and result.model_calls==1


def test_real_fact_sources_are_attached_by_code_and_not_written_by_model():
    source=RecordSource(record_id="report",file_name="지난 MT.pdf",location=SourceLocation(label="1쪽"))
    fact=RecordFact(content="작년은 숙소를 알아봤다",sources=(source,))
    model=Model(composition(assumptions=[dict(content="과거 숙소 검토 경험을 참고해 장소 조사를 포함",fact_ids=["f1"])]))
    result=asyncio.run(run_plan_generation(request(reference_facts=(fact,)),invoke=model))
    assert result.preview.assumptions[0].sources==(source,)
    assert "file_name" not in json.loads(model.calls[0][0][1].content)["reference_facts"][0]


@pytest.mark.parametrize("step",[
    dict(code="EVENT_DAY",purpose="당일",starts_at="2027-03-23T09:00:00+09:00"),
    dict(code="RESEARCH_VENUE",purpose="장소",deadline="2027-03-23T09:00:00+09:00"),
    dict(code="SETTLE_EXPENSES",purpose="정산",starts_at="2027-03-19T09:00:00+09:00"),
    dict(code="RECRUIT_NOTICE",purpose="모집",starts_at="2027-03-10T09:00:00+09:00",
         deadline="2027-03-09T09:00:00+09:00"),
    dict(code="RECRUIT_NOTICE",purpose="모집",deadline="2027-03-10T09:00:00+09:00",
         actions=[dict(type="NOTICE",title="안내",due_date="2027-03-11")]),
])
def test_known_dates_reject_wrong_day_reversed_period_and_action_outside_period(step):
    req=request(basis_draft=PlanningDraft(conditions=PlanningConditions(event_type="MT",start_date="2027-03-20",end_date="2027-03-21")))
    assert asyncio.run(run_plan_generation(req,invoke=Model(composition(steps=[step])))).status=="failed"


def test_dates_are_compared_in_requested_timezone():
    req=request(basis_draft=PlanningDraft(conditions=PlanningConditions(event_type="MT",start_date="2027-03-20")))
    result=asyncio.run(run_plan_generation(req,invoke=Model(composition(steps=[
        dict(code="EVENT_DAY",purpose="당일",starts_at="2027-03-19T16:00:00+00:00")]))))
    assert result.status=="generated"  # 한국 시각으로 3월 20일


def test_missing_type_skips_model_and_timeout_has_no_provider_detail():
    model=Model()
    result=asyncio.run(run_plan_generation(request(basis_draft=PlanningDraft()),invoke=model))
    assert result.status=="needs_clarification" and not model.calls
    result=asyncio.run(run_plan_generation(request(),invoke=Model(AITimeoutError("provider-detail"))))
    assert result.status=="failed" and "provider-detail" not in result.model_dump_json()


@pytest.mark.parametrize("error",[AIConfigError("configuration"),PermissionError("denied"),RuntimeError("unexpected")])
def test_non_retryable_errors_propagate(error):
    with pytest.raises(type(error)):
        asyncio.run(run_plan_generation(request(),invoke=Model(error)))


def test_button_has_direct_entrypoint_and_successful_retry_reuses_preview():
    model=Model()
    generate=partial(run_plan_generation,invoke=model)
    req=ButtonPlanGenerationRequest(request_id="click-1",draft=request().basis_draft,reference_date="2026-10-24")
    first=asyncio.run(run_button_plan_generation(req,generate=generate))
    second=asyncio.run(run_button_plan_generation(ButtonPlanGenerationRequest(**{
        **req.model_dump(),"generation":first.generation}),generate=generate))
    assert first.result.status==second.result.status=="generated" and len(model.calls)==1
    assert second.result.preview.id==first.result.preview.id and second.result.model_calls==0
    assert first.generation.preview.trigger.source=="button"
    assert all(m.__class__.__name__!="AIMessage" for m in model.calls[0][0])


def test_button_failed_change_guard_override_failure_preservation_and_request_id_reuse():
    req=ButtonPlanGenerationRequest(request_id="click-1",draft=request().basis_draft,reference_date="2026-10-24")
    model=Model()
    generate=partial(run_plan_generation,invoke=model)
    first=asyncio.run(run_button_plan_generation(req,generate=generate))
    state=PlanningGenerationState(preview=first.result.preview,condition_change_pending=True)
    blocked=ButtonPlanGenerationRequest(**{**req.model_dump(),"request_id":"click-2","generation":state})
    assert asyncio.run(run_button_plan_generation(blocked,generate=generate)).result.status=="needs_clarification"
    assert len(model.calls)==1
    failed=asyncio.run(run_button_plan_generation(ButtonPlanGenerationRequest(**{
        **blocked.model_dump(),"use_current_conditions":True}),generate=partial(run_plan_generation,invoke=Model(AITimeoutError("detail")))))
    assert failed.result.status=="failed" and failed.generation==state
    # 같은 클릭 ID를 다른 조건의 새 요청에 재활용하면 기존 초안을 조용히 반환하지 않는다.
    changed=ButtonPlanGenerationRequest(**{**req.model_dump(),"generation":first.generation,
        "draft":PlanningDraft(conditions=PlanningConditions(event_type="MT",headcount=40))})
    assert asyncio.run(run_button_plan_generation(changed,generate=generate)).result.status=="needs_clarification"


def test_injected_generator_cannot_replace_basis_or_trigger():
    good=asyncio.run(run_plan_generation(request(),invoke=Model()))
    async def wrong(req): return good
    req=ButtonPlanGenerationRequest(request_id="another-click",draft=request().basis_draft,reference_date="2026-10-24")
    result=asyncio.run(run_button_plan_generation(req,generate=wrong))
    assert result.result.status=="failed" and result.generation.preview is None
