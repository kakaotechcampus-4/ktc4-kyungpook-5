"""#269: v7/v8 메시지 순서 비교 실행기를 고정 응답으로 검증한다(모델 호출 없음)."""

import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import SystemMessage

from app.ai.features.planning.agent import graph, nodes
from app.ai.scripts import compare_agent_context_layout as compare
from app.ai.tests.test_planning_latency_runner import fixed_models  # noqa: F401

SETTINGS = SimpleNamespace(model='fixed-model', request_timeout_seconds=60)


def events(directory):
    return [json.loads(line) for line in (directory / 'attempts.jsonl').read_text().splitlines()]


def recording(monkeypatch):
    """고정 모델 앞에서 실제로 보낸 메시지를 남긴다. 변형 이름은 그때 패치된 순서 함수로 구분한다."""
    seen, fixed = [], graph.call_agent_model
    async def invoke(messages, **kwargs):
        layout = 'v7' if nodes.agent_messages is compare.legacy_v7_messages else 'v8'
        seen.append((layout, messages))
        return await fixed(messages, **kwargs)
    monkeypatch.setattr(graph, 'call_agent_model', invoke)
    return seen


def test_schedule_alternates_case_and_variant_order():
    plan = compare.schedule(rounds=2, controls=1)
    warmup = [item for item in plan if item[0] == 'warmup']
    first = [item[3:] for item in plan if item[:2] == ('measurement', 1)]
    second = [item[3:] for item in plan if item[:2] == ('measurement', 2)]
    controls = [item for item in plan if item[0] == 'control']
    assert len(warmup) == 6
    assert first == [('C1', 'v7'), ('C1', 'v8'), ('C2', 'v7'), ('C2', 'v8'), ('G1', 'v7'), ('G1', 'v8')]
    assert second == [('G1', 'v8'), ('G1', 'v7'), ('C2', 'v8'), ('C2', 'v7'), ('C1', 'v8'), ('C1', 'v7')]
    assert len(controls) == 2 * len(compare.CONTROLS)
    assert 'generation_only' not in {item[3] for item in controls}


def test_v7_puts_context_in_first_message_and_v8_at_the_end(tmp_path, fixed_models, monkeypatch):
    seen = recording(monkeypatch)
    report = asyncio.run(compare.run_session(tmp_path / 'out', session_id='t', rounds=1, controls=0,
                                             interval=0, settings=SETTINGS))
    assert report['status'] == 'completed' and report['finished'] == 12
    assert nodes.agent_messages is not compare.legacy_v7_messages  # 요청이 끝나면 현재 코드로 돌아온다.
    for layout, messages in seen:
        first, last = messages[0], messages[-1]
        if layout == 'v7':
            assert first.content.startswith(nodes.PROMPT + '\n\n현재 실행 문맥(JSON 데이터):\n')
            assert not isinstance(last, SystemMessage)
        else:
            assert first.content == nodes.PROMPT
            assert isinstance(last, SystemMessage) and last.content.startswith('현재 실행 문맥(JSON 데이터):\n')
    assert {layout for layout, _ in seen} == {'v7', 'v8'}
    latency = report['summary']['latency']
    for variant in compare.VARIANTS:
        for case_id in compare.CASE_IDS:
            assert latency[variant][case_id]['counts']['success'] == 1  # 준비 실행은 집계하지 않는다.
            assert latency[variant][case_id]['observation']['by_stage']['agent_model']['usage'] is not None


def test_control_cases_are_recorded_with_boundary_checks(tmp_path, fixed_models):
    report = asyncio.run(compare.run_session(tmp_path / 'out', session_id='t', rounds=1, controls=1,
                                             interval=0, settings=SETTINGS))
    finished = [row for row in events(tmp_path / 'out') if row['event'] == 'finished' and row['phase'] == 'control']
    assert len(finished) == 2 * len(compare.CONTROLS)
    assert all('checks' in row and 'passed' in row for row in finished)
    controls = report['summary']['controls']
    assert sum(group['started'] for variant in controls.values() for group in variant.values()) == len(finished)
