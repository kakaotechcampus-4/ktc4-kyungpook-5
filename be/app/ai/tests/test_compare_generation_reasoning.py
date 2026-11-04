"""#264: 생성 모델 추론 깊이 비교 실행기를 고정 응답으로 검증한다(모델 호출 없음)."""

import asyncio
import json
from types import SimpleNamespace

from app.ai.features.planning.generation import model as generation_model
from app.ai.scripts import compare_generation_reasoning as compare
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
