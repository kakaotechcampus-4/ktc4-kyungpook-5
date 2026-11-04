"""#280: --dry-run은 모델 없이 입력 확인. 실제 실행은 4사례 × invoke/stream, 재시도 없음."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
import time
from pathlib import Path
from langchain_core.messages import AIMessage, message_chunk_to_message
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import agent_tool_schemas
from app.ai.features.planning.state_codec import to_agent_input
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request

async def inputs():
    fixture = load_fixture()
    captured = []
    for name in ('C1', 'C2', 'mixed'):
        case = next(c for c in fixture.cases if c.id == ('C2' if name == 'mixed' else name))
        req = make_request(fixture, case, 'stream-probe-' + name)
        if name == 'mixed':
            req = req.model_copy(update={'message': req.message.model_copy(update={'content':
                '인원을 60명으로 바꾸기 전에 무엇을 할지 짧게 설명하고 변경해 줘.'})})
        calls = 0
        async def fake(messages, *, allow_tools):
            nonlocal calls
            captured.append((name + ('-after-tool' if calls else ''), messages))
            calls += 1
            if name == 'C2' and calls == 1:
                return AIMessage(content='', tool_calls=[dict(id='probe-condition', name='update_event_conditions', args={
                    'changes': [dict(op='SET', change=dict(field='headcount', value=60), status='specified',
                        evidence=dict(message_id=req.message.id, quote=req.message.content))]})])
            return AIMessage(content='고정 답변')
        async def unused(*args):
            raise AssertionError('진단 입력 구성에서 생성 금지')
        await run_planning_agent_turn(to_agent_input(req), invoke=fake, generate=unused)
    return captured

def describe(message):
    blocks = []
    for block in message.content if isinstance(message.content, list) else []:
        if not isinstance(block, dict):
            continue
        item = {k: block[k] for k in ('type', 'index', 'phase') if k in block}
        item['keys'] = sorted(block)
        if block.get('type') == 'text':
            item['text'] = block.get('text', '')
        blocks.append(item)
    return dict(blocks=blocks, tool_count=len(message.tool_calls), invalid_tool_count=len(message.invalid_tool_calls),
        tool_names=[call['name'] for call in message.tool_calls],
        tool_chunks=bool(getattr(message, 'tool_call_chunks', [])),
        status=message.response_metadata.get('status'), usage=message.usage_metadata)

async def main(args):
    cases = await inputs()
    if args.dry_run:
        print(json.dumps({'cases': [c[0] for c in cases], 'max_http_attempts': 8}, ensure_ascii=False))
        return
    if args.output is None:
        raise ValueError('--output 필요')
    args.output.mkdir(parents=True, exist_ok=False)
    from app.ai.llm import build_chat_model
    model = build_chat_model(max_retries=0)
    bound = model.bind_tools(agent_tool_schemas(search_enabled=False, generation_enabled=True),
                             parallel_tool_calls=True, tool_choice='auto')
    report = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), model=model.model_name,
        versions={p: importlib.metadata.version(p) for p in ('langgraph', 'langchain-core', 'langchain-openai', 'openai')},
        max_retries=0, attempts=[])
    for index, (name, messages) in enumerate(cases):
        for mode in (('invoke', 'stream') if index % 2 == 0 else ('stream', 'invoke')):
            row = dict(case=name, mode=mode, chunks=[])
            start = time.perf_counter()
            try:
                if mode == 'invoke':
                    response = await bound.ainvoke(messages)
                else:
                    combined = None
                    async for chunk in bound.astream(messages):
                        row['chunks'].append(dict(ms=round((time.perf_counter()-start)*1000, 2), **describe(chunk)))
                        combined = chunk if combined is None else combined + chunk
                    response = message_chunk_to_message(combined)
                row['result'] = describe(response)
            except Exception as error:
                row['error_type'] = type(error).__name__
            row['elapsed_ms'] = round((time.perf_counter()-start)*1000, 2)
            report['attempts'].append(row)
            (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(name, mode, row.get('error_type', row.get('result', {}).get('status')), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path)
    asyncio.run(main(parser.parse_args()))
