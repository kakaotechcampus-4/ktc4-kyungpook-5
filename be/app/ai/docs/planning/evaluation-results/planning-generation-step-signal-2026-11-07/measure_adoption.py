"""#389 채택 측정: 단계 신호를 더한 새 경로가 기존 경로보다 느려지지 않고, 신호가 최종 초안과 맞는가.

be/에서 실행: .venv/bin/python -I <이 파일> <출력.json> [라운드 수, 기본 10]

- 두 경로 모두 진행 포트를 넘겨 공개 함수(G2 generate_planning_preview, G1 chat_planning)를 부른다.
- 기존 경로: entrypoints의 StepCodeReader 자리에 아무것도 찾지 않는 읽기를 잠시 끼운다.
  generation_writing까지는 develop(#388)과 같고 generation_step은 오지 않는다. 모델 요청은 두 경로가 같다.
- 새 경로: 코드 그대로. 같은 라운드 안에서 경로·사례 순서를 번갈아 순서 효과를 줄인다(#111). #388 채택 측정과 같은 일정이다.
- 진행 이벤트의 종류·상태와 단계 신호의 위치·코드를 남긴다. 모델이 쓴 글은 남기지 않는다.
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
from app.ai.features.planning.generation import entrypoints
from app.ai.scripts.planning_latency_inputs import load_fixture, make_request

clock = {'t0': 0.0, 'events': []}
NewReader = entrypoints.StepCodeReader


class NoStepReader:
    # 기존 경로: 글은 받되 단계 코드를 찾지 않는다.
    def feed(self, text):
        return []


def mark(kind, **data):
    clock['events'].append(dict(ms=round((time.perf_counter() - clock['t0']) * 1000, 1), kind=kind, **data))


class Port:
    async def progress(self, event):
        step = dict(index=event.step.index, code=event.step.code) if event.step else None
        mark('progress', progress_kind=event.kind, status=event.status, step=step)

    async def reply_delta(self, text):
        pass

    async def reply_reset(self):
        pass


def schedule(rounds):
    # 'before' = 기존 경로, 'after' = 새 경로
    plan = [('warmup', 0, case, path) for case in ('G2', 'G1') for path in ('before', 'after')]
    for number in range(1, rounds + 1):
        paths = ('before', 'after') if number % 2 else ('after', 'before')
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
        entrypoints.StepCodeReader = NoStepReader if path == 'before' else NewReader
        request = make_request(fixture, cases[case_id], f'adoption-{index}')
        call = generate_planning_preview if case_id == 'G2' else chat_planning
        clock.update(t0=time.perf_counter(), events=[])
        preview_codes = excluded_codes = None
        try:
            result = await call(request, progress=Port())
            generation = result.view.generation_result
            error, status = None, generation.status if generation else None
            if generation and generation.preview:
                preview_codes = [str(step.code) for step in generation.preview.steps]
                excluded_codes = [str(step.code) for step in generation.preview.excluded_steps]
        except Exception as cause:
            error, status = type(cause).__name__, None
        mark('end')
        report['attempts'].append(dict(phase=phase, round=number, case=case_id, path=path, error=error,
                                       generation_status=status, preview_codes=preview_codes,
                                       excluded_codes=excluded_codes, events=clock['events']))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        steps = sum(e.get('progress_kind') == 'generation_step' for e in clock['events'])
        print(phase, number, case_id, path, error or status, 'step signals', steps, flush=True)
        await asyncio.sleep(1)
    entrypoints.StepCodeReader = NewReader
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10))
