"""#198: 고정 이름을 붙이되 생성 선택과 저장된 대화는 바꾸지 않는다."""

import json
from functools import partial

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.ai import (
    AITimeoutError, PlanningPreviewRequest, PlanningPublicResult,
    PlanningResumeState, PlanningUserMessage, chat_planning,
    generate_planning_preview, parse_resume_state,
)
from app.ai.contracts import ExcludedPlanStep, ExcludedPreviewStep
from app.ai.features.planning import public_workflow as workflow
from app.ai.features.planning.agent.nodes import GENERATE_TOOL_NAME
from app.ai.features.planning.generation.catalog import CATALOG
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.generation.schemas import PlanComposition
from app.ai.planning_catalog import PLANNING_STEP_NAMES
from app.ai.tests.test_plan_generation_graph import Model, composition, request as generation_request
from app.ai.tests.test_planning_public_workflow import button, request, run, scripted, tool


def without_names(value):
    """이전 버전의 실제 저장 형식을 재현한다. 입력 객체는 그대로 둔다."""
    data = json.loads(value.model_dump_json())

    def strip(item):
        if isinstance(item, dict):
            for excluded in item.get('excluded_steps', []):
                excluded.pop('name', None)
            for child in item.values():
                strip(child)
        elif isinstance(item, list):
            for child in item:
                strip(child)

    strip(data)
    return data


def assert_names(preview):
    assert preview is not None
    assert all(item.name == PLANNING_STEP_NAMES[item.code] for item in preview.excluded_steps)


@pytest.mark.parametrize('included', ['EVENT_DAY', 'RESEARCH_VENUE'])
def test_generation_attaches_names_without_asking_model_or_changing_selection(included):
    raw = composition(steps=[dict(code=included, purpose='이번 행사에 필요한 단계')])
    before = raw.model_dump_json()
    model = Model(raw)
    result = run(run_plan_generation(generation_request(), invoke=model))
    assert result.status == 'generated'
    assert_names(result.preview)
    assert [(x.code, x.reason) for x in result.preview.excluded_steps] == [
        (x.code, x.reason) for x in raw.excluded_steps
    ]
    assert raw.model_dump_json() == before
    assert len(model.calls) == result.model_calls == 1
    # name은 최종 응답의 필드다. LLM이 작성하는 구조화 출력에는 추가하지 않는다.
    schema = model.calls[0][1].model_json_schema()
    assert set(schema['$defs']['ExcludedPlanStep']['properties']) == {'code', 'reason'}
    assert model.calls[0][1] is PlanComposition


def test_model_output_cannot_write_the_display_name():
    with pytest.raises(ValidationError):
        ExcludedPlanStep(code='DEMAND_SURVEY', reason='이번에는 생략', name='다른 이름')
    assert 'name' in ExcludedPreviewStep.model_json_schema()['required']


def test_legacy_names_are_derived_without_mutating_the_original_payload():
    for entry in CATALOG:
        old = dict(code=entry.code.value, reason='운영진이 검토할 제외 사유')
        assert ExcludedPreviewStep.model_validate(old).name == entry.name
        assert old == dict(code=entry.code.value, reason='운영진이 검토할 제외 사유')
    assert len(PLANNING_STEP_NAMES) == len(CATALOG) == 13
    with pytest.raises(TypeError):
        PLANNING_STEP_NAMES['DEMAND_SURVEY'] = '변경된 이름'


@pytest.mark.parametrize('name', ['다른 이름', '', ' ', None])
def test_invalid_explicit_names_are_not_silently_repaired(name):
    with pytest.raises(ValidationError):
        ExcludedPreviewStep.model_validate(dict(code='DEMAND_SURVEY', reason='제외 사유', name=name))


@pytest.mark.parametrize('code', ['UNKNOWN', 'CANCEL_RECORD', None, [], {}])
def test_invalid_legacy_codes_remain_validation_errors(code):
    with pytest.raises(ValidationError):
        ExcludedPreviewStep.model_validate(dict(code=code, reason='제외 사유'))


def test_old_public_result_state_and_request_restore_then_reuse_without_generation(monkeypatch):
    # 대화를 한 번 나눈 뒤 생성해, 이름 보완 과정에서 이력이 사라지지 않는지도 본다.
    scripted(monkeypatch, [AIMessage(content='현재 조건으로 초안을 만들 수 있어요.')])
    chat = run(chat_planning(request()))
    model = Model()
    monkeypatch.setattr(workflow, 'run_plan_generation', partial(run_plan_generation, invoke=model))
    first = run(generate_planning_preview(button(request(), resume_state=chat.next_state)))
    old = without_names(first.next_state)
    original = json.dumps(old, ensure_ascii=False)
    restored = parse_resume_state(original)
    assert restored.schema_version == 1
    assert_names(restored.payload.generation.preview)
    assert restored == PlanningResumeState.model_validate_json(original)
    assert restored.payload.history == first.next_state.payload.history
    assert restored.payload.basis_draft == first.next_state.payload.basis_draft
    assert restored.payload.generation.preview.id == first.next_state.payload.generation.preview.id
    assert PlanningPublicResult.model_validate(without_names(first)) == first
    # BE가 parse 함수를 따로 부르지 않고 공개 요청에 JSON dict를 넣어도 같은 결과다.
    req = PlanningPreviewRequest.model_validate({**button(request()).model_dump(), 'resume_state': old})
    second = run(generate_planning_preview(req))
    assert second.view.generation_result.preview == first.view.generation_result.preview
    assert second.view.generation_result.model_calls == 0
    assert len(model.calls) == 1
    assert json.dumps(old, ensure_ascii=False) == original


def test_failed_regeneration_preserves_restored_preview(monkeypatch):
    monkeypatch.setattr(workflow, 'run_plan_generation', partial(run_plan_generation, invoke=Model()))
    first = run(generate_planning_preview(button(request())))
    old = parse_resume_state(json.dumps(without_names(first.next_state)))
    monkeypatch.setattr(workflow, 'run_plan_generation',
                        partial(run_plan_generation, invoke=Model(AITimeoutError('timeout'))))
    failed = run(generate_planning_preview(button(request(), request_id='retry-2', resume_state=old)))
    assert failed.view.generation_result.status == 'failed'
    assert failed.view.generation_result.preview is None
    assert failed.next_state.payload.generation.preview == first.next_state.payload.generation.preview
    assert_names(failed.next_state.payload.generation.preview)


def test_chat_tool_generation_returns_the_same_named_contract(monkeypatch):
    model = Model()
    monkeypatch.setattr(workflow, 'run_plan_generation', partial(run_plan_generation, invoke=model))
    scripted(monkeypatch, [tool(GENERATE_TOOL_NAME, dict(quote='초안 만들어줘')),
                           AIMessage(content='계획 초안을 만들었어요.')])
    result = run(chat_planning(request(message=PlanningUserMessage(id='u1', content='초안 만들어줘'))))
    assert result.view.generation_result.status == 'generated'
    assert result.view.generation_result.preview.trigger.source == 'chat'
    assert_names(result.view.generation_result.preview)
    assert result.next_state.payload.generation.preview == result.view.generation_result.preview
    assert len(model.calls) == 1
