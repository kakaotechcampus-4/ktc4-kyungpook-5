"""#280: SDK 조립, 최종 답변 선택, Graph/저장 왕복을 실제 모델 없이 고정한다."""
import asyncio
from copy import deepcopy

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from functools import partial

import app.ai as ai
from app.ai import llm
from app.ai.llm_stream import final_answer_text
from app.ai.features.planning.agent import nodes
from app.ai.features.planning.progress import reply_delta, reply_reset
from app.ai.tests.test_planning_public_workflow import request
from app.ai.tests.test_planning_progress import Recorder


def chunk(text='', phase=None, index=0, **kwargs):
    block = dict(type='text', text=text, index=index)
    if phase is not None:
        block['phase'] = phase
    return AIMessageChunk(content=[block], **kwargs)


def done(status='completed', **metadata):
    return AIMessageChunk(content=[], response_metadata=dict(status=status, **metadata))


def tool_chunks():
    return [AIMessageChunk(content=[dict(type='function_call', index=1, name='update_event_conditions',
                arguments='', call_id='t1', id='fc1')],
            tool_call_chunks=[dict(index=1, name='update_event_conditions', args='', id='t1')]),
        AIMessageChunk(content=[dict(type='function_call', index=1, arguments='{"changes":[]}')],
            tool_call_chunks=[dict(index=1, args='{"changes":[]}')])]


class Model:
    def __init__(self, chunks, *, before=None):
        self.chunks = chunks
        self.before = before
        self.closed = False
        self.options = None

    def bind_tools(self, tools, **kwargs):
        self.options = kwargs
        return self

    async def astream(self, messages):
        try:
            for i, item in enumerate(self.chunks):
                if self.before:
                    self.before(i)
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self.closed = True


class Output(Recorder):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.parts = []
        self.resets = 0

    async def reply_delta(self, text):
        self.parts.append(text)

    async def reply_reset(self):
        self.parts.clear()
        self.resets += 1


def run(model, output=None, **kwargs):
    output = output or Output()
    response = asyncio.run(llm.astream_with_tools([], tools=[], model=model,
        on_text=output.reply_delta, on_reset=output.reply_reset, **kwargs))
    return response, output


def test_phase_prefix_streams_before_completion_and_normalizes_storage():
    out = Output()
    pieces = [chunk(phase='final_answer', id='r1'), chunk('안녕'), chunk('하세요'),
              chunk('', id='r1'), done()]
    def before(i):
        if i == 4:
            assert ''.join(out.parts) == '안녕하세요'
    model = Model(pieces, before=before)
    response, out = run(model, out, parallel_tool_calls=True)
    assert out.parts == ['안녕', '하세요']
    assert response.content == [dict(type='text', text='안녕하세요', phase='final_answer', annotations=[])]
    assert model.closed and model.options == dict(parallel_tool_calls=True, tool_choice='auto')


def test_commentary_and_reasoning_are_not_displayed_but_history_is_preserved():
    response, out = run(Model([AIMessageChunk(content=[dict(type='reasoning', index=0,
        summary=[dict(type='summary_text', text='internal', index=0)])]),
        chunk('작업 설명', 'commentary', 1), chunk('', 'final_answer', 2), chunk('최종 답변', index=2), done()]))
    assert out.parts == ['최종 답변']
    assert final_answer_text(response) == '최종 답변'
    assert response.content[1]['text'] == '작업 설명'
    assert response.content[0]['summary'] == [dict(type='summary_text', text='internal')]


@pytest.mark.parametrize('late_phase', [False, True])
def test_unknown_or_late_phase_buffers_until_completed(late_phase):
    out = Output()
    pieces = [chunk('답변')]
    if late_phase:
        pieces.append(chunk(phase='final_answer'))
    pieces.append(done())
    def before(i):
        assert not out.parts
    response, out = run(Model(pieces, before=before), out)
    assert out.parts == ['답변'] and final_answer_text(response) == '답변'


def test_tool_after_text_resets_and_never_streams_arguments():
    response, out = run(Model([chunk('임시 답변', 'final_answer'), *tool_chunks(), done()]))
    assert out.resets == 1 and not out.parts
    assert response.tool_calls[0]['args'] == {'changes': []}
    assert response.content[-1]['arguments'] == '{"changes":[]}'
    assert 'index' not in response.content[-1]


def test_tool_start_is_reported_once_per_call_before_arguments_finish():
    # 조각은 누적돼 accept에 다시 들어온다. 같은 호출 ID는 한 번만, 이름과 ID가 있는 첫 조각에서 알린다.
    second = [AIMessageChunk(content=[dict(type='function_call', index=2, name='search_past_events',
                  arguments='', call_id='t2', id='fc2')],
              tool_call_chunks=[dict(index=2, name='search_past_events', args='', id='t2')]),
              AIMessageChunk(content=[dict(type='function_call', index=2, arguments='{"query":"MT"}')],
              tool_call_chunks=[dict(index=2, args='{"query":"MT"}')])]
    started = []
    seen_args = []
    async def on_tool_start(name, call_id):
        started.append((name, call_id))
    model = Model([*tool_chunks(), *second, done()])
    model.before = lambda i: seen_args.append(len(started))
    response, out = run(model, on_tool_start=on_tool_start)
    assert started == [('update_event_conditions', 't1'), ('search_past_events', 't2')]
    # 첫 조건 조각 다음(인자 조각이 오기 전)에 이미 시작을 알렸다.
    assert seen_args[1] == 1
    assert [c['id'] for c in response.tool_calls] == ['t1', 't2'] and not out.parts


def test_text_only_answer_reports_no_tool_start():
    started = []
    async def on_tool_start(name, call_id):
        started.append(name)
    run(Model([chunk('좋아요', 'final_answer'), done()]), on_tool_start=on_tool_start)
    assert not started


def test_tool_only_has_no_reply_or_reset():
    response, out = run(Model([*tool_chunks(), done()]))
    assert response.tool_calls and not out.parts and not out.resets


@pytest.mark.parametrize('tail,error', [
    ([], ai.AIInvalidResponseError),
    ([done('incomplete')], ai.AIInvalidResponseError),
    ([done('incomplete', incomplete_details={'reason': 'max_output_tokens'})], ai.AIOutputLimitError),
    ([RuntimeError('internal')], RuntimeError),
    # 응답 도중 공급자 error 이벤트: SDK는 HTTP 상태 없는 APIError를 낸다.
    ([openai.APIError('server_error', request=httpx.Request('POST', 'https://model.test'), body=None)],
     ai.AIRetryableError),
])
def test_unfinished_stream_resets_and_closes(tail, error):
    out = Output()
    model = Model([chunk('작성 중', 'final_answer'), *tail])
    with pytest.raises(error):
        run(model, out)
    assert out.resets == 1 and not out.parts and model.closed


@pytest.mark.parametrize('pieces', [[], [done()], [chunk(' ', 'final_answer'), done()],
    [chunk('중간 설명', 'commentary'), done()],
    [AIMessageChunk(content=[dict(type='refusal', refusal='거절')]), done()],
    [AIMessageChunk(content='', tool_call_chunks=[dict(name='bad', args='not-json', id='t1', index=0)]), done()]])
def test_empty_refusal_and_invalid_tool_are_not_success(pieces):
    with pytest.raises(ai.AIInvalidResponseError):
        run(Model(pieces))


def test_disallowed_tools_and_cancellation():
    model = Model([*tool_chunks(), done()])
    with pytest.raises(ai.AIInvalidResponseError):
        run(model, allow_tools=False)
    assert model.options['tool_choice'] == 'none'
    cancelled = Model([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        run(cancelled)
    assert cancelled.closed


def test_usage_is_retained_without_inventing_zero():
    pieces = [chunk('답변', 'final_answer'), done()]
    response, _ = run(Model(pieces))
    assert response.usage_metadata is None
    pieces[-1].usage_metadata = dict(input_tokens=10, output_tokens=2, total_tokens=12)
    response, _ = run(Model(pieces))
    assert response.usage_metadata['total_tokens'] == 12


def test_safe_port_callbacks_do_not_break_turn_or_log_payload(caplog):
    class Broken:
        async def reply_delta(self, text):
            raise RuntimeError('private text')
        async def reply_reset(self):
            raise RuntimeError('private text')
    async def scenario():
        response = await llm.astream_with_tools([], tools=[], model=Model([chunk('답변', 'final_answer'), done()]),
            on_text=partial(reply_delta, Broken()), on_reset=partial(reply_reset, Broken()))
        await reply_reset(Broken())
        return response
    assert asyncio.run(scenario()).text == '답변'
    assert 'private text' not in caplog.text


def test_public_invoke_and_stream_store_identical_history_and_restore(monkeypatch):
    # SDK의 실제 response 형태처럼 text ID/annotations를 지정해 전송용 index만 다르게 한다.
    req = request()
    args = dict(changes=[dict(op='SET', change=dict(field='headcount', value=50), status='tentative',
        evidence=dict(message_id='u1', quote=req.message.content))])
    import json
    tool_block = dict(type='function_call', id='fc1', call_id='t1', name='update_event_conditions', arguments=json.dumps(args))
    text_block = dict(type='text', id='msg1', text='50명으로 잡았어요.', phase='final_answer', annotations=[])
    messages = [AIMessage(id='r1', content=[tool_block], tool_calls=[dict(id='t1', name='update_event_conditions', args=args)]),
                AIMessage(id='r2', content=[text_block])]
    iterator = iter(deepcopy(messages))
    async def invoke(*args, **kwargs):
        return next(iterator)
    monkeypatch.setattr(nodes, 'ainvoke_with_tools', invoke)
    monkeypatch.setattr(nodes, 'ToolMessage', partial(ToolMessage, id='tool-result'))
    baseline = asyncio.run(ai.chat_planning(req))
    responses = iter([
        [AIMessageChunk(id='r1', content=[dict(tool_block, index=0)],
            tool_call_chunks=[dict(index=0, id='t1', name='update_event_conditions', args=json.dumps(args))]), done()],
        [chunk('', 'final_answer', id='r2'), chunk('50명으로 '), chunk('잡았어요.'),
         AIMessageChunk(content=[dict(type='text', text='', id='msg1', index=0)]), done()],
    ])
    class SequenceModel:
        def bind_tools(self, *args, **kwargs):
            return Model(next(responses))
    monkeypatch.setattr(llm, 'get_chat_model', lambda: SequenceModel())
    out = Output()
    streamed = asyncio.run(ai.chat_planning(req, progress=out))
    assert streamed == baseline
    assert ''.join(out.parts) == streamed.view.reply
    # 스트림은 Tool 첫 조각에서 시작을, 검증·반영 뒤 같은 호출 ID로 완료를 알린다(#290).
    assert [(e.kind, e.status, e.operation_id) for e in out.events] == [
        ('condition_started', 'running', 't1'), ('condition_applied', 'completed', 't1')]
    restored = ai.parse_resume_state(streamed.next_state.model_dump_json())
    assert restored == baseline.next_state
    # 다음 턴에 복원한 Tool 호출과 결과를 모델이 실제로 받는지 확인한다.
    seen = []
    async def next_invoke(messages, **kwargs):
        seen.extend(messages)
        return AIMessage(content='앞선 조건을 이어갈게요.')
    monkeypatch.setattr(nodes, 'ainvoke_with_tools', next_invoke)
    next_req = req.model_copy(update={'draft': streamed.view.draft, 'resume_state': restored,
        'message': ai.PlanningUserMessage(id='u2', content='왜 바꿨어?')})
    asyncio.run(ai.chat_planning(next_req))
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == 't1' for m in seen)


def test_api_connection_error_uses_existing_error_type_and_resets():
    import httpx
    import openai
    out = Output()
    error = openai.APIConnectionError(request=httpx.Request('POST', 'https://example.invalid'))
    with pytest.raises(ai.AIRetryableError):
        run(Model([chunk('답변', 'final_answer'), error]), out)
    assert not out.parts and out.resets == 1


def test_unknown_earlier_block_does_not_reorder_progressive_answer():
    out = Output()
    pieces = [chunk('앞부분', index=0), chunk('뒷부분', 'final_answer', 1),
              chunk('', 'final_answer', 0), done()]
    def before(i):
        assert not out.parts
    response, out = run(Model(pieces, before=before), out)
    assert ''.join(out.parts) == final_answer_text(response) == '앞부분뒷부분'


def test_probe_dry_inputs_have_four_cases_without_model_calls():
    from app.ai.scripts.check_planning_stream import inputs, describe
    cases = asyncio.run(inputs())
    assert [name for name, _ in cases] == ['C1', 'C2', 'C2-after-tool', 'mixed']
    summary = describe(AIMessage(content=[dict(type='reasoning', summary=[{'text': 'secret'}],
        encrypted_content='private', id='r1')]))
    assert 'secret' not in str(summary) and 'private' not in str(summary)


def test_stream_and_invoke_select_same_mixed_answer():
    expected = AIMessage(content=[dict(type='text', text='설명', phase='commentary', annotations=[]),
                                 dict(type='text', text='결과', phase='final_answer', annotations=[])])
    response, out = run(Model([chunk('설명', 'commentary'), chunk('결과', 'final_answer', 1), done()]))
    assert response.content == expected.content
    assert final_answer_text(expected) == final_answer_text(response) == ''.join(out.parts) == '결과'
