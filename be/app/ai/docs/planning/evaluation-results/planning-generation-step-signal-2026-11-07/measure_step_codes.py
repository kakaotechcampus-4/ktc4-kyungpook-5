"""#389 기준 측정: 생성 모델은 단계 코드를 맨 앞에 쓰나, 단계 코드는 작성 구간의 어디쯤 나오나. 코드 변경 없이 관찰만 한다.

be/에서 실행: .venv/bin/python -I <이 파일> <출력.json> [라운드 수, 기본 10]

- #388 measure_writing_start.py와 같은 입력·순서로 공개 함수(G2 버튼, G1 채팅)를 진행 포트와 함께 부른다.
- 생성 모델에 기록용 콜백만 끼운다. 조각마다 도착 시각과 지금까지 받은 글자 수만 적고, 글자는 메모리에만 모은다.
- 응답이 끝나면 모은 글에서 아래를 찾고 글은 버린다. 파일에는 위치·시각·카탈로그 코드만 남는다(모델이 쓴 문장은 남기지 않는다).
  1) 최상위 첫 키가 "steps"인가, 단계마다 첫 키가 "code"인가 (스키마 순서를 모델이 그대로 따르는가)
  2) 단계 i의 code 값이 끝나는 글자 위치 → 그 글자가 든 조각의 도착 시각
  3) steps 배열이 끝나는 위치(= "excluded_steps" 키가 시작되는 곳) → 시각
"""
import asyncio
import json
import re
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


# 오프라인 분석이라 완성된 글 전체를 본다. 문자열 안의 \"code\"는 앞에 역슬래시가 붙어 여기에 걸리지 않는다.
# 그래도 순서대로 찾은 코드가 파싱한 steps의 코드와 같은지 마지막에 대조해, 다르면 matched=False로 남긴다.
CODE_VALUE = re.compile(r'(?<!\\)"code"\s*:\s*"([A-Z_]+)"')
EXCLUDED_KEY = re.compile(r'(?<!\\)"excluded_steps"\s*:')


def analyze(text: str, timeline: list[tuple[float, int]]) -> dict:
    """완성된 계획 JSON과 (조각 도착 ms, 그때까지 받은 글자 수) 목록으로 단계 코드가 나온 시각을 구한다."""
    def arrived(offset: int):
        # offset 번째 글자(0부터)까지 받은 첫 조각의 도착 시각
        return next((ms for ms, total in timeline if total > offset), None)

    try:
        pairs = json.loads(text, object_pairs_hook=lambda items: items)
    except ValueError:
        return dict(parsed=False)
    top_keys = [key for key, _ in pairs]
    steps = dict(pairs).get('steps') or []
    step_first_keys = [step[0][0] if step else None for step in steps]
    codes = [dict(step).get('code') for step in steps]
    matches = list(CODE_VALUE.finditer(text))[:len(codes)]
    excluded = EXCLUDED_KEY.search(text)
    return dict(
        parsed=True,
        top_keys=top_keys,
        steps_first=top_keys[:1] == ['steps'],
        code_first_all=all(key == 'code' for key in step_first_keys),
        codes=codes,
        matched=[m.group(1) for m in matches] == codes,
        # 닫는 따옴표 위치 = code 값이 끝난 순간. 제품 읽기 코드가 신호를 낼 자리다.
        code_end_ms=[arrived(m.end() - 1) for m in matches],
        steps_end_ms=arrived(excluded.start()) if excluded else None,
        text_chars=len(text),
    )


class ChunkRecorder(AsyncCallbackHandler):
    async def on_chat_model_start(self, serialized, messages, **kwargs):
        clock['call'] = dict(start=now_ms(), first_text=None, last_text=None, end=None, status=None)
        clock['text'], clock['timeline'] = [], []
        mark('generation_model_start')

    async def on_llm_new_token(self, token, *, chunk=None, **kwargs):
        blocks = chunk.message.content if chunk is not None and isinstance(chunk.message.content, list) else []
        text = ''.join(b.get('text', '') for b in blocks if isinstance(b, dict) and b.get('type') == 'text')
        if not text:
            return
        at = now_ms()
        call = clock['call']
        call['first_text'] = call['first_text'] or at
        call['last_text'] = at
        clock['text'].append(text)
        previous = clock['timeline'][-1][1] if clock['timeline'] else 0
        clock['timeline'].append((at, previous + len(text)))

    async def on_llm_end(self, response, **kwargs):
        call = clock['call']
        call['end'] = now_ms()
        call['status'] = response.generations[0][0].message.response_metadata.get('status')
        call['text_chunks'] = len(clock['timeline'])
        call['analysis'] = analyze(''.join(clock['text']), clock['timeline'])
        clock['text'] = []  # 글은 남기지 않는다
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
    # #388과 같다: 예열 1번씩은 집계에서 빼고, 라운드마다 사례 순서를 뒤집는다(#111).
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
        request = make_request(fixture, cases[case_id], f'steps-{index}')
        call = generate_planning_preview if case_id == 'G2' else chat_planning
        clock.update(t0=time.perf_counter(), events=[], call=None)
        preview_codes = None
        try:
            result = await call(request, progress=Port())
            generation = result.view.generation_result
            error, status = None, generation.status if generation else None
            if generation and generation.preview:
                # 최종 초안(P2 「준비 순서」)의 코드 순서. 신호 순서와 대조한다.
                preview_codes = [step.code for step in generation.preview.steps]
        except Exception as cause:
            error, status = type(cause).__name__, None
        mark('end')
        report['attempts'].append(dict(phase=phase, round=number, case=case_id, error=error,
                                       generation_status=status, preview_codes=preview_codes,
                                       model_call=clock['call'], events=clock['events']))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        analysis = (clock['call'] or {}).get('analysis') or {}
        print(phase, number, case_id, error or status, 'steps_first', analysis.get('steps_first'),
              'code_first', analysis.get('code_first_all'), 'matched', analysis.get('matched'), flush=True)
        await asyncio.sleep(1)
    report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    asyncio.run(main(Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10))
