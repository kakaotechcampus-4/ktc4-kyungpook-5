"""#388 기준 측정: 생성 모델의 「생각 중」과 「작성 중」은 각각 얼마나 걸리나. 코드 변경 없이 관찰만 한다.

be/에서 실행: .venv/bin/python -I <이 파일> <출력.json> [라운드 수, 기본 10]

- 공개 함수(버튼 G2: generate_planning_preview, 채팅 G1: chat_planning)를 제품과 같이 진행 포트와 함께 부른다.
- 생성 모델을 만드는 build_plan_model에 기록용 콜백만 끼운다. streaming=True 모델은 ainvoke로 불러도
  조각마다 on_llm_new_token을 부르므로, 제품 경로(ainvoke_structured)를 바꾸지 않고 조각 도착 시각을 적을 수 있다.
- 조각마다 내용 블록 종류(text / reasoning / 없음)를 보고, 글자가 처음 온 시각과 글자 조각 수를 센다.
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from langchain_core.callbacks import AsyncCallbackHandler

from app.ai import chat_planning, generate_planning_preview
from app.ai.config import AISettings
from app.ai.features.planning.generation import model as generation_model
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request

clock = {'t0': 0.0, 'events': []}


def now_ms() -> float:
    return round((time.perf_counter() - clock['t0']) * 1000, 1)


def mark(kind, **data):
    clock['events'].append(dict(ms=now_ms(), kind=kind, **data))


class ChunkRecorder(AsyncCallbackHandler):
    """생성 모델 한 번의 조각 도착을 기록한다. 원문은 남기지 않고 블록 종류와 글자 수만 센다."""

    async def on_chat_model_start(self, serialized, messages, **kwargs):
        clock['call'] = dict(start=now_ms(), first_chunk=None, first_reasoning=None, first_text=None,
                             last_text=None, text_chunks=0, text_chars=0, reasoning_chunks=0, end=None, usage=None)
        mark('generation_model_start')

    async def on_llm_new_token(self, token, *, chunk=None, **kwargs):
        call, at = clock['call'], now_ms()
        if call['first_chunk'] is None:
            call['first_chunk'] = at
        blocks = chunk.message.content if chunk is not None and isinstance(chunk.message.content, list) else []
        text = ''.join(b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text')
        if any(isinstance(b, dict) and b.get('type') == 'reasoning' for b in blocks):
            call['reasoning_chunks'] += 1
            call['first_reasoning'] = call['first_reasoning'] or at
        if text:
            call['text_chunks'] += 1
            call['text_chars'] += len(text)
            call['first_text'] = call['first_text'] or at
            call['last_text'] = at

    async def on_llm_end(self, response, **kwargs):
        call = clock['call']
        call['end'] = now_ms()
        message = response.generations[0][0].message
        usage = getattr(message, 'usage_metadata', None) or {}
        call['usage'] = dict(output=usage.get('output_tokens'),
                             reasoning=(usage.get('output_token_details') or {}).get('reasoning'))
        call['status'] = message.response_metadata.get('status')
        mark('generation_model_end')


original_build = generation_model.build_plan_model


def build_with_recorder(settings=None, **overrides):
    return original_build(settings, callbacks=[ChunkRecorder()], **overrides)


generation_model.build_plan_model = build_with_recorder


class Port:
    async def progress(self, event):
        mark('progress', progress_kind=event.kind, status=event.status)

    async def reply_delta(self, text):
        pass

    async def reply_reset(self):
        pass


def schedule(rounds):
    # 예열 1번씩은 집계에서 뺀다. 라운드마다 순서를 뒤집어 순서 효과를 줄인다(#111).
    plan = [('warmup', 0, 'G2'), ('warmup', 0, 'G1')]
    for number in range(1, rounds + 1):
        plan += [('measurement', number, case) for case in (('G2', 'G1') if number % 2 else ('G1', 'G2'))]
    return plan


async def main(output: Path, rounds: int):
    settings = AISettings()
    settings.require_api()
    fixture = load_fixture()
    cases = {case.id: case for case in fixture.cases}
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--', 'app/ai/features', 'app/ai/llm.py'], text=True).strip())
    report = dict(model=settings.model, commit=commit, product_code_dirty=dirty, rounds=rounds,
                  started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), attempts=[])
    for index, (phase, number, case_id) in enumerate(schedule(rounds), 1):
        request = make_request(fixture, cases[case_id], f'writing-{index}')
        call = generate_planning_preview if case_id == 'G2' else chat_planning
        clock.update(t0=time.perf_counter(), events=[], call=None)
        try:
            result = await call(request, progress=Port())
            generation = result.view.generation_result
            error, status = None, generation.status if generation else None
        except Exception as cause:
            error, status = type(cause).__name__, None
        mark('end')
        report['attempts'].append(dict(phase=phase, round=number, case=case_id, error=error,
                                       generation_status=status, model_call=clock['call'], events=clock['events']))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(phase, number, case_id, error or status, flush=True)
        await asyncio.sleep(1)
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


asyncio.run(main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10))
