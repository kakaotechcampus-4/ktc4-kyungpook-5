"""#265: single/multi 비교 실행기를 고정 응답으로 검증한다(모델 호출 없음)."""

import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai.features.planning.agent import graph, nodes
from app.ai.scripts import compare_parallel_tool_calls as compare
from app.ai.tests.test_planning_latency_runner import fixed_models  # noqa: F401

SETTINGS = SimpleNamespace(model='fixed-model', request_timeout_seconds=60)


def c2_model(monkeypatch):
    """C2에서 설정이 켜져 있으면 변경+보류를 한 응답에, 꺼져 있으면 두 응답에 나눠 낸다."""
    seen = []
    async def invoke(messages, **kwargs):
        seen.append(nodes.PARALLEL_TOOL_CALLS)
        start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        user = messages[start]
        tools = [m for m in messages[start:] if isinstance(m, ToolMessage)]  # 이번 턴의 Tool 결과만 센다.
        change = dict(id=f'set-{user.id}', name=nodes.TOOL_NAME, args=dict(changes=[dict(
            op='SET', change=dict(field='headcount', value=60), status='specified',
            evidence=dict(message_id=user.id, quote='예상 참가 인원을 60명으로 바꿔줘.'))]))
        defer = dict(id=f'defer-{user.id}', name=nodes.OFFER_TOOL_NAME, args=dict(
            action='defer', reason='사용자가 만들지 말라고 함',
            evidence=dict(message_id=user.id, quote='계획 초안은 만들지 마.')))
        if nodes.PARALLEL_TOOL_CALLS and not tools:
            return AIMessage(content='', tool_calls=[change, defer])
        if not nodes.PARALLEL_TOOL_CALLS and len(tools) < 2:
            return AIMessage(content='', tool_calls=[[change, defer][len(tools)]])
        return AIMessage(content='60명으로 바꿨고 초안은 말씀하실 때 만들게요.')
    monkeypatch.setattr(graph, 'call_agent_model', invoke)
    return seen


def test_schedule_alternates_variant_order():
    plan = compare.schedule(rounds=2, controls=1)
    assert [item[4] for item in plan if item[0] == 'warmup'] == ['single', 'multi']
    assert [item[4] for item in plan if item[:2] == ('measurement', 1)] == ['single', 'multi']
    assert [item[4] for item in plan if item[:2] == ('measurement', 2)] == ['multi', 'single']
    assert len([item for item in plan if item[0] == 'control']) == 2 * len(compare.CONTROLS)
    only = compare.schedule(rounds=0, controls=2, warmup=False, control_ids=['date_resume'])
    assert only == [('control', 1, 'boundary', 'date_resume', 'single'), ('control', 1, 'boundary', 'date_resume', 'multi'),
                    ('control', 2, 'boundary', 'date_resume', 'multi'), ('control', 2, 'boundary', 'date_resume', 'single')]


def test_records_tool_batches_per_response_and_restores_setting(tmp_path, fixed_models, monkeypatch):
    seen = c2_model(monkeypatch)
    report = asyncio.run(compare.run_session(tmp_path / 'out', session_id='t', rounds=2, controls=0,
                                             interval=0, settings=SETTINGS))
    assert report['status'] == 'completed' and report['finished'] == 6
    assert nodes.PARALLEL_TOOL_CALLS is True and {False, True} <= set(seen)
    latency = report['summary']['latency']
    for variant, calls, batches in (('single', 3, 'update_event_conditions | update_generation_offer'),
                                    ('multi', 2, 'update_event_conditions+update_generation_offer')):
        group = latency[variant]
        assert group['counts']['started'] == group['counts']['success'] == 2  # 준비 실행은 집계하지 않는다.
        assert group['observation']['model_call_attempts']['agent_model'] == 2 * calls
        assert group['tool_batches']['patterns'] == {batches: 2}
        assert group['tool_batches']['bundled'] == (2 if variant == 'multi' else 0)
        offer = json.loads(next(iter(group['offers'])))
        assert offer == dict(status='deferred', basis_matches_draft=True)


def test_control_cases_are_recorded_with_boundary_checks(tmp_path, fixed_models):
    report = asyncio.run(compare.run_session(tmp_path / 'out', session_id='t', rounds=1, controls=1,
                                             interval=0, settings=SETTINGS))
    rows = [json.loads(line) for line in (tmp_path / 'out' / 'attempts.jsonl').read_text().splitlines()]
    finished = [row for row in rows if row['event'] == 'finished' and row['phase'] == 'control']
    assert len(finished) == 2 * len(compare.CONTROLS)
    assert all('checks' in row and 'passed' in row for row in finished)
    assert sum(group['started'] for variant in report['summary']['controls'].values()
               for group in variant.values()) == len(finished)
