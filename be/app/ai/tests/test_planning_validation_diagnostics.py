"""실패한 같은 초안을 키/API 없이 재검사하며, 수집이 실제 요청 흐름을 바꾸지 않게 한다."""

import asyncio
from functools import partial
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import ValidationError
import pytest

from app.ai import AITimeoutError, PlanningPreviewRequest, PlanningResumeState
from app.ai.config import AISettings
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph, nodes
from app.ai.features.planning.generation import graph, schemas
from app.ai.features.planning.generation.validation import PlanValidationError
from app.ai.scripts import check_planning_generation_requests as check
from app.ai.scripts import planning_validation_diagnostics as diag
from app.ai.scripts.replay_planning_validation import replay_file
from app.ai.scripts.planning_latency_observation import install_observers
from app.ai.tests.test_plan_generation_graph import composition, Model
from app.ai.tests.test_plan_validation_details import examples


def last_turn(messages):
    """실행 문맥(시스템 메시지)이 맨 끝에 붙어도(planning-agent-v8, #269) 마지막 대화 메시지를 본다."""
    return next(m for m in reversed(messages) if not isinstance(m, SystemMessage))


def button_request(internal):
    draft = internal.basis_draft
    topics = tuple(topic for topic, field in [('dates', 'start_date'), ('headcount', 'headcount'), ('location', 'location')]
                   if getattr(draft.conditions, field) is None)
    draft = draft.model_copy(update={'deferred_topics': topics})
    state = PlanningResumeState(**{k: check.CONTEXT[k] for k in ('club_id', 'event_id', 'conversation_id')},
                                payload=dict(basis_draft=draft))
    return PlanningPreviewRequest(**check.CONTEXT, request_id='diagnostic-button', base_revision=0,
                                  draft=draft, resume_state=state)


def collect(request):
    with diag.capture_validation_failures(request, run_id='test', model='injected-model') as captured, install_observers():
        row, interrupted = asyncio.run(check.attempt(request))
    assert not interrupted
    return captured, row


@pytest.mark.parametrize('rule,path,internal,answer', examples(), ids=[x[0] for x in examples()])
def test_each_rule_roundtrips_and_replays_without_any_model(monkeypatch, tmp_path, rule, path, internal, answer):
    request = button_request(internal)
    model = Model(answer)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=model))
    captured, row = collect(request)
    assert not captured.errors and len(captured.snapshots) == 1 and len(model.calls) == 1
    assert row['generation_status'] == 'failed'
    snapshot = captured.snapshots[0]
    assert snapshot.violation.rule == rule and snapshot.violation.path == path
    assert snapshot.generation_attempt == 1
    span = next(s for s in row['observation']['spans'] if s['id'] == snapshot.validation_span_id)
    assert span['stage'] == 'validate_plan' and span['parent_id'] == snapshot.generation_span_id
    assert snapshot.input.messages == () and snapshot.composition.model_dump(mode='json') == answer.model_dump(mode='json')
    saved = tmp_path / 'failure.json'
    diag.write_snapshot(saved, snapshot)
    raw = saved.read_bytes()
    assert 'messages' not in json.loads(raw)['input']

    def forbidden(*args, **kwargs):
        pytest.fail('재검사는 API나 설정을 호출하면 안 됩니다')

    monkeypatch.setattr(AISettings, '__init__', forbidden)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', forbidden)
    import app.ai.llm as llm
    monkeypatch.setattr(llm, 'get_chat_model', forbidden)
    monkeypatch.chdir(tmp_path)
    replay = replay_file(saved, tmp_path / 'replay.json')
    assert replay['status'] == 'rejected' and replay['reproduced'] and replay['same_validator_source']
    assert replay['expected_violation'] == replay['actual_violation']
    assert saved.read_bytes() == raw
    with pytest.raises(FileExistsError):
        diag.write_snapshot(saved, snapshot)


def retry_models(monkeypatch, request, answers):
    iterator = iter(answers)
    calls = []
    count = 0

    async def invoke(messages, schema):
        calls.append(messages)
        answer = next(iterator)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def agent(messages, **kwargs):
        nonlocal count
        if isinstance(last_turn(messages), ToolMessage):
            status = json.loads(last_turn(messages).content).get('status')
            if status == 'generated' or count >= len(answers):
                return AIMessage(content='실제 결과를 확인해 주세요.')
        count += 1
        user = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
        return AIMessage(content='', tool_calls=[check.tool(nodes.GENERATE_TOOL_NAME,
                        dict(quote=user.text), f'diagnostic-generate-{count}')])

    monkeypatch.setattr(agent_graph, 'call_agent_model', agent)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=invoke))
    return calls


def chat_request():
    fixture = check.validate_fixture(json.loads(check.DEFAULT_FIXTURE.read_text()))
    return check.make_request(fixture, 'changed_headcount', 'chat', 'diagnostic-chat')


def test_failed_attempts_survive_agent_retry_and_final_success(monkeypatch):
    request = chat_request()
    wrong_day = composition(steps=[dict(code='EVENT_DAY', purpose='틀린 날짜', starts_at='2026-11-08T09:00:00+09:00')])
    calls = retry_models(monkeypatch, request, [composition(excluded_steps=[]), wrong_day, composition()])
    captured, row = collect(request)
    assert row['outcome'] == 'success' and len(calls) == 3 and not captured.errors
    assert [s.generation_attempt for s in captured.snapshots] == [1, 2]
    assert [s.violation.rule for s in captured.snapshots] == ['catalog_partition', 'event_start_mismatch']
    assert len({s.generation_span_id for s in captured.snapshots}) == 2
    assert all(diag.replay_snapshot(s)['reproduced'] for s in captured.snapshots)


def test_model_failure_is_not_fabricated_as_validation_failure(monkeypatch):
    request = chat_request()
    retry_models(monkeypatch, request, [AITimeoutError('private-provider-body')])
    captured, row = collect(request)
    assert row['generation_status'] == 'failed' and row['failure_category'] == 'timeout'
    assert not captured.snapshots and not captured.errors
    assert 'private-provider-body' not in json.dumps(row)


def test_hashes_and_schema_reject_edited_saved_material(monkeypatch, tmp_path):
    rule, path, internal, answer = examples()[7]
    request = button_request(internal)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=Model(answer)))
    captured, _ = collect(request)
    saved = tmp_path / 'failure.json'
    diag.write_snapshot(saved, captured.snapshots[0])
    data = json.loads(saved.read_text())
    data['composition']['steps'][0]['starts_at'] = '2026-11-07T09:00:00+09:00'
    with pytest.raises(ValidationError):
        diag.ValidationSnapshot.model_validate(data)
    data = json.loads(saved.read_text())
    data['artifact_version'] = 99
    with pytest.raises(ValidationError):
        diag.ValidationSnapshot.model_validate(data)


def test_replay_distinguishes_changed_behavior_from_reproduction(monkeypatch):
    _, _, internal, answer = examples()[7]
    request = button_request(internal)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=Model(answer)))
    captured, _ = collect(request)
    snapshot = captured.snapshots[0]
    monkeypatch.setattr(graph, 'validate_plan', lambda state: {})
    report = diag.replay_snapshot(snapshot)
    assert report['status'] == 'accepted' and not report['reproduced']


def test_collector_restores_functions_and_never_replaces_original_error():
    _, _, internal, answer = examples()[7]
    request = button_request(internal)
    original = graph.validate_plan
    with diag.capture_validation_failures(request, run_id='test', model=None) as captured:
        with pytest.raises(RuntimeError):
            with diag.capture_validation_failures(request, run_id='overlap', model=None):
                pass
        with pytest.raises(PlanValidationError):
            graph.validate_plan(dict(request=internal, composition=answer))
    assert graph.validate_plan is original
    assert captured.errors == ['missing_observation_context'] and not captured.snapshots


def test_snapshot_construction_error_keeps_the_original_p1_result(monkeypatch):
    _, _, internal, answer = examples()[7]
    request = button_request(internal)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=Model(answer)))

    def broken(**kwargs):
        raise ValueError('private-diagnostic-message')

    monkeypatch.setattr(diag, 'ValidationSnapshot', broken)
    captured, row = collect(request)
    assert row['generation_status'] == 'failed' and row['failure_category'] == 'invalid_plan'
    assert captured.errors == ['ValueError'] and not captured.snapshots
    assert 'private-diagnostic-message' not in json.dumps(row)


def test_snapshot_serialization_error_keeps_the_original_p1_result(monkeypatch):
    _, _, internal, answer = examples()[7]
    request = button_request(internal)
    monkeypatch.setattr(public_workflow, 'run_plan_generation', partial(graph.run_plan_generation, invoke=Model(answer)))

    def broken(*args, **kwargs):
        raise RuntimeError('private-serialization-message')

    monkeypatch.setattr(schemas.PlanComposition, 'model_dump', broken)
    captured, row = collect(request)
    assert row['generation_status'] == 'failed' and row['failure_category'] == 'invalid_plan'
    assert captured.errors == ['RuntimeError'] and not captured.snapshots
    assert 'private-serialization-message' not in json.dumps(row)


def test_drafts_recorded_before_276_with_cancel_codes_still_replay(tmp_path):
    # 11-04 G1 실측의 실제 실패 원본. 저장 당시 형식(v1)은 CANCEL_*를 허용했다.
    # 지금 생성 형식은 이 초안을 읽지 못하지만, 재검사는 같은 catalog_partition 거절을 다시 확인해야 한다.
    source = (diag.AI_DIR / 'docs/planning/evaluation-results/planning-generation-reasoning-2026-11-04'
              / 'g1-chat/session-03/validation/g1-reasoning-03-measurement-003-G1-low-1.json')
    snapshot = diag.ValidationSnapshot.model_validate_json(source.read_bytes())
    assert {x.code for x in snapshot.composition.excluded_steps} == {
        'CANCEL_NOTIFY_PARTICIPANTS', 'CANCEL_VENUE', 'CANCEL_REFUND', 'CANCEL_RECORD'}
    with pytest.raises(ValidationError):
        schemas.PlanComposition.model_validate(snapshot.composition.model_dump(mode='json'))
    report = replay_file(source, tmp_path / 'replay.json')
    assert report['status'] == 'rejected' and report['reproduced'] is True
    assert report['actual_violation']['rule'] == 'catalog_partition'
