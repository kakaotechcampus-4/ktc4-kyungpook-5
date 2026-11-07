"""#264: 생성 모델 추론 깊이 비교 실행기를 고정 응답으로 검증한다(모델 호출 없음)."""

import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.features.planning.agent import graph as agent_graph
from app.ai.features.planning.agent.nodes import GENERATE_TOOL_NAME
from app.ai.features.planning.generation import model as generation_model
from app.ai.scripts import compare_generation_reasoning as compare
from app.ai.scripts.planning_latency_inputs import load_fixture
from app.ai.tests.test_plan_generation_graph import composition

SETTINGS = SimpleNamespace(model='fixed-model', request_timeout_seconds=60)


def events(directory):
    return [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]


def fixed_generation(monkeypatch):
    """실제 invoke_plan_composition 경로를 그대로 타게 하고, 모델 객체 생성과 호출만 고정한다.

    low 변형에는 날짜 미정인데 날짜를 넣은 초안을 돌려줘 검증 거절(dates_when_unknown)을 만든다.
    """
    built = []
    monkeypatch.setattr(generation_model, 'build_chat_model', lambda settings=None, **params: SimpleNamespace(**params))

    async def ainvoke_structured(messages, schema, *, model):
        built.append(model)
        if model.reasoning == {'effort': 'low'}:
            return composition(steps=[dict(code='RESEARCH_VENUE', purpose='합성', starts_at='2026-11-06T09:00:00+09:00')])
        return composition()

    monkeypatch.setattr(generation_model, 'ainvoke_structured', ainvoke_structured)
    return built


def test_schedule_alternates_variant_order():
    plan = compare.schedule(rounds=2)
    assert plan == [('warmup', 0, 'default'), ('warmup', 0, 'low'),
                    ('measurement', 1, 'default'), ('measurement', 1, 'low'),
                    ('measurement', 2, 'low'), ('measurement', 2, 'default')]


def test_variant_changes_only_reasoning(monkeypatch):
    monkeypatch.setattr(generation_model, 'build_chat_model', lambda settings=None, **params: params)
    default, low = compare.variant_builder('default')(), compare.variant_builder('low')()
    assert default == dict(max_tokens=generation_model.PLAN_MAX_OUTPUT_TOKENS, streaming=True, reasoning=None)
    assert low == dict(default, reasoning={'effort': 'low'})


def test_session_sends_variant_setting_and_records_violation_rule(tmp_path, monkeypatch):
    built = fixed_generation(monkeypatch)
    output = tmp_path / 'out'
    report = asyncio.run(compare.run_session(output, session_id='t', rounds=2, interval=0, settings=SETTINGS))
    assert report['status'] == 'completed' and report['finished'] == 6
    # 요청이 끝나면 현재 코드의 build_plan_model로 돌아온다.
    assert generation_model.build_plan_model is compare.BUILD_PLAN_MODEL
    finished = [row for row in events(output) if row['event'] == 'finished']
    assert [row['variant'] for row in finished] == ['default', 'low', 'default', 'low', 'low', 'default']
    assert [model.reasoning for model in built] == [None if row['variant'] == 'default' else {'effort': 'low'}
                                                    for row in finished]
    assert all(model.max_tokens == generation_model.PLAN_MAX_OUTPUT_TOKENS and model.streaming for model in built)
    for row in finished:
        if row['variant'] == 'default':
            assert row['outcome'] == 'success' and row['violations'] == []
        else:
            assert row['outcome'] == 'failed' and row['failure']['category'] == 'invalid_plan'
            [violation] = row['violations']
            assert violation['rule'] == 'dates_when_unknown' and (output / violation['file']).exists()
        assert row['capture_errors'] == []
    summary = report['summary']
    assert summary['default']['latency']['counts']['success'] == 2  # 준비 실행은 집계하지 않는다.
    assert summary['default']['success_step_count']['median'] == 2
    assert summary['low']['latency']['counts']['failed'] == 2
    assert summary['low']['violations'] == {'dates_when_unknown': 2}
    assert summary['low']['success_step_count'] == dict(n=0, median=None, min=None, max=None)
    assert report['environment']['model_options']['reasoning'] == dict(default=None, low={'effort': 'low'})


def test_chat_case_goes_through_agent_and_same_generation_setting(tmp_path, monkeypatch):
    """G1은 대화 모델이 생성 Tool을 고른 뒤 같은 생성 경로(build_plan_model)를 탄다."""
    built = fixed_generation(monkeypatch)
    offer_id = load_fixture().resume_state.payload.generation.offer.id

    async def agent(messages, **kwargs):
        latest = next(m for m in reversed(messages) if not isinstance(m, SystemMessage))
        if isinstance(latest, HumanMessage) and latest.content == '응, 만들어줘.':
            return AIMessage(content='', tool_calls=[dict(id='generate-1', name=GENERATE_TOOL_NAME,
                                                          args=dict(quote=latest.content, offer_id=offer_id))])
        return AIMessage(content='초안을 만들었어요.')

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    output = tmp_path / 'out'
    report = asyncio.run(compare.run_session(output, session_id='t', case_id='G1', rounds=1, interval=0,
                                             settings=SETTINGS))
    finished = [row for row in events(output) if row['event'] == 'finished']
    assert report['profile']['case_id'] == 'G1' and [row['case_id'] for row in finished] == ['G1'] * 4
    assert [model.reasoning for model in built] == [None, {'effort': 'low'}, None, {'effort': 'low'}]
    stages = {span['stage'] for row in finished for span in row['observation']['spans']}
    assert {'agent_model', 'generation_model'} <= stages
    assert [row['outcome'] for row in finished] == ['success', 'failed', 'success', 'failed']
    assert report['summary']['low']['violations'] == {'dates_when_unknown': 1}


# --- #276: 출력 형식 v1/v2 비교 ---------------------------------------------------------

from langchain_core.outputs import ChatGeneration, LLMResult

from app.ai.errors import AIInvalidResponseError
from app.ai.features.planning.generation import graph as generation_graph, schemas
from app.ai.features.planning.generation.catalog import CATALOG
from app.ai.scripts import generation_output_v1
from app.ai.scripts.planning_latency_observation import CURRENT_TRACE, PARENT_SPAN

CANCEL_CODES = ('CANCEL_NOTIFY_PARTICIPANTS', 'CANCEL_VENUE', 'CANCEL_REFUND', 'CANCEL_RECORD')


def cancel_answer():
    """11-04 G1 실패와 같은 모양: 13단계를 모두 넣고 CANCEL_* 4개를 뺀 단계로 적은 응답."""
    return dict(steps=[dict(code=x.code.value, purpose='필요') for x in CATALOG],
                excluded_steps=[dict(code=code, reason='현재 취소 조건이 없음') for code in CANCEL_CODES])


def test_step_code_variants_differ_only_in_output_schema_and_both_use_low(monkeypatch):
    monkeypatch.setattr(generation_model, 'build_chat_model', lambda settings=None, **params: params)
    seen = {}
    for name in ('v1', 'v2'):
        with compare.variant_patches(name, 'step-codes'):
            seen[name] = (generation_model.build_plan_model(), generation_graph.PlanComposition,
                          generation_graph.PROMPT_VERSION)
    assert seen['v1'][0] == seen['v2'][0] == dict(max_tokens=generation_model.PLAN_MAX_OUTPUT_TOKENS, streaming=True,
                                                  reasoning={'effort': 'low'})
    assert seen['v1'][1:] == (generation_output_v1.PlanComposition, 'planning-generation-v1')
    assert seen['v2'][1:] == (schemas.PlanComposition, 'planning-generation-v2')
    # 요청이 끝나면 현재 코드로 돌아온다.
    assert generation_graph.PlanComposition is schemas.PlanComposition
    assert generation_model.build_plan_model is compare.BUILD_PLAN_MODEL


def test_v1_output_schema_offers_cancel_codes_and_v2_does_not():
    def codes(schema):
        found = set()
        def walk(node):
            if isinstance(node, dict):
                found.update(node.get('enum', []))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
        walk(schema.model_json_schema())
        return {code for code in found if code in compare.PLANNING_STEP_NAMES or code.startswith('CANCEL_')}
    assert codes(generation_output_v1.PlanComposition) == set(compare.PLANNING_STEP_NAMES) | set(CANCEL_CODES)
    assert codes(schemas.PlanComposition) == set(compare.PLANNING_STEP_NAMES)


def test_step_code_session_separates_plan_rejection_and_output_failure(tmp_path, monkeypatch):
    """같은 CANCEL 응답이 v1에서는 계획 검사 거절, v2에서는 출력 형식 실패로 끝나는지 기록한다."""
    monkeypatch.setattr(generation_model, 'build_chat_model', lambda settings=None, **params: SimpleNamespace(**params))
    schemas_sent = []

    async def ainvoke_structured(messages, schema, *, model):
        schemas_sent.append(schema)
        # 실제 SDK처럼 받은 형식으로 응답을 읽는다. v2는 CANCEL_*를 읽지 못해 출력 형식 오류가 된다.
        try:
            return schema.model_validate(cancel_answer())
        except Exception as error:
            raise AIInvalidResponseError('형식 불일치') from error

    monkeypatch.setattr(generation_model, 'ainvoke_structured', ainvoke_structured)
    output = tmp_path / 'out'
    report = asyncio.run(compare.run_session(output, session_id='t', comparison='step-codes', rounds=2, interval=0,
                                             settings=SETTINGS))
    finished = [row for row in events(output) if row['event'] == 'finished']
    assert [row['variant'] for row in finished] == ['v1', 'v2', 'v1', 'v2', 'v2', 'v1']
    assert [schema is generation_output_v1.PlanComposition for schema in schemas_sent] == [
        row['variant'] == 'v1' for row in finished]
    for row in finished:
        if row['variant'] == 'v1':
            assert row['failure']['category'] == 'invalid_plan'
            [violation] = row['violations']
            saved = json.loads((output / violation['file']).read_text())
            assert violation['rule'] == 'catalog_partition'
            assert saved['generation_prompt_version'] == 'planning-generation-v1'
        else:
            assert row['failure']['category'] == 'invalid_output' and row['violations'] == []
    assert report['comparison'] == 'step-codes'
    assert report['generation_prompt_versions'] == dict(v1='planning-generation-v1', v2='planning-generation-v2')
    assert report['environment']['model_options']['reasoning'] == dict(v1={'effort': 'low'}, v2={'effort': 'low'})
    assert report['summary']['v1']['violations'] == {'catalog_partition': 2}
    assert report['summary']['v2']['failures'] == {'invalid_output': 2}


def test_outside_catalog_codes_are_read_only_from_generation_model_responses():
    found = []
    recorder = compare.OutsideCodeRecorder(found)
    text = json.dumps(cancel_answer(), ensure_ascii=False)
    response = LLMResult(generations=[[ChatGeneration(message=AIMessage(content=text))]])
    trace = SimpleNamespace(spans=[dict(id=1, stage='generation_model'), dict(id=2, stage='agent_model')])
    trace_token, span_token = CURRENT_TRACE.set(trace), PARENT_SPAN.set(2)
    try:
        asyncio.run(recorder.on_llm_end(response))  # 대화 모델 응답은 보지 않는다.
        assert found == []
        PARENT_SPAN.set(1)
        asyncio.run(recorder.on_llm_end(response))
        asyncio.run(recorder.on_llm_end(response))  # 같은 코드는 한 번만 남긴다.
    finally:
        PARENT_SPAN.reset(span_token)
        CURRENT_TRACE.reset(trace_token)
    assert found == list(CANCEL_CODES)
