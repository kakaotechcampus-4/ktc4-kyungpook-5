"""#388 채택 측정: 새 경로(astream_structured)가 기존 경로(ainvoke_structured)보다 느려지지 않는가.

be/에서 실행: .venv/bin/python -I <이 파일> <출력.json> [라운드 수, 기본 10]

- 두 경로 모두 진행 포트를 넘겨 공개 함수(G2 generate_planning_preview, G1 chat_planning)를 부른다.
- 기존 경로: generation.model의 astream_structured 자리에 on_first_text를 무시하고 ainvoke_structured를 부르는
  함수를 잠시 끼운다. 바꾸기 전 코드와 같은 모델 호출이 되고 generation_writing은 오지 않는다.
- 새 경로: 코드 그대로. 같은 라운드 안에서 경로·사례 순서를 번갈아 순서 효과를 줄인다(#111).
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from app.ai import chat_planning, generate_planning_preview
from app.ai.config import AISettings
from app.ai.features.planning.generation import model as generation_model
from app.ai.llm import ainvoke_structured
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request

clock = {'t0': 0.0, 'events': []}
new_stream = generation_model.astream_structured


async def old_invoke(messages, schema, *, on_first_text, model):
    # 바꾸기 전 경로: 완성본만 받는다. 첫 글자 알림은 부르지 않는다.
    return await ainvoke_structured(messages, schema, model=model)


def mark(kind, **data):
    clock['events'].append(dict(ms=round((time.perf_counter() - clock['t0']) * 1000, 1), kind=kind, **data))


class Port:
    async def progress(self, event):
        mark('progress', progress_kind=event.kind, status=event.status)

    async def reply_delta(self, text):
        pass

    async def reply_reset(self):
        pass


def schedule(rounds):
    plan = [('warmup', 0, case, path) for case in ('G2', 'G1') for path in ('invoke', 'stream')]
    for number in range(1, rounds + 1):
        paths = ('invoke', 'stream') if number % 2 else ('stream', 'invoke')
        cases = ('G2', 'G1') if number % 2 else ('G1', 'G2')
        plan += [('measurement', number, case, path) for case in cases for path in paths]
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
    for index, (phase, number, case_id, path) in enumerate(schedule(rounds), 1):
        generation_model.astream_structured = old_invoke if path == 'invoke' else new_stream
        request = make_request(fixture, cases[case_id], f'adoption-{index}')
        call = generate_planning_preview if case_id == 'G2' else chat_planning
        clock.update(t0=time.perf_counter(), events=[])
        try:
            result = await call(request, progress=Port())
            generation = result.view.generation_result
            error, status = None, generation.status if generation else None
            steps = len(generation.preview.steps) if generation and generation.preview else None
        except Exception as cause:
            error, status, steps = type(cause).__name__, None, None
        mark('end')
        report['attempts'].append(dict(phase=phase, round=number, case=case_id, path=path, error=error,
                                       generation_status=status, steps=steps, events=clock['events']))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(phase, number, case_id, path, error or status, flush=True)
        await asyncio.sleep(1)
    generation_model.astream_structured = new_stream
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


asyncio.run(main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10))
