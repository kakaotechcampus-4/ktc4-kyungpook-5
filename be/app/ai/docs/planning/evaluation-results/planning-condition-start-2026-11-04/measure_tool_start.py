"""3-2 측정: 조건 Tool 첫 조각이 완료 이벤트보다 얼마나 먼저 오는가. 코드 변경 없이 관찰만 한다.

be/에서 실행: .venv/bin/python -I <이 파일> <출력.json>
- llm_stream.ReplyStream.accept를 감싸 Tool 호출 조각이 처음 보인 시각(이름·ID)을 기록한다.
- 진행 포트로 completed 이벤트 시각과 operation_id를 기록해 첫 조각 ID와 같은지 본다.
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from app.ai import (PlanningChatRequest, PlanningConditions, PlanningDraft, PlanningUserMessage,
                    chat_planning)
from app.ai import llm_stream
from app.ai.config import AISettings

CASES = {
    'A 이름': '행사 이름은 2026년 MT로 해 줘',
    'B 인원': '인원은 35명으로 바꿔 줘',
    'C 인원+일정': '인원은 40명으로, 일정은 12월 5일부터 1박 2일로 해 줘',
}
ROUNDS = 3

clock = {'t0': 0.0, 'events': []}


def mark(kind, **data):
    clock['events'].append(dict(ms=round((time.perf_counter() - clock['t0']) * 1000), kind=kind, **data))


original_accept = llm_stream.ReplyStream.accept


async def accept(self, combined):
    seen = getattr(self, '_seen_tool_ids', None)
    if seen is None:
        seen = self._seen_tool_ids = set()
        mark('model_first_chunk')
    for chunk in combined.tool_call_chunks or []:
        key = chunk.get('id') or f"index-{chunk.get('index')}"
        if key not in seen and chunk.get('name'):
            seen.add(key)
            mark('tool_first_chunk', name=chunk.get('name'), id=chunk.get('id'))
    return await original_accept(self, combined)


llm_stream.ReplyStream.accept = accept


class Port:
    def __init__(self):
        self.replied = False

    async def progress(self, event):
        mark('progress', progress_kind=event.kind, status=event.status, id=event.operation_id, text=event.text)

    async def reply_delta(self, text):
        if not self.replied:
            self.replied = True
            mark('reply_first_delta')

    async def reply_reset(self):
        mark('reply_reset')


async def main(output: Path):
    settings = AISettings()
    settings.require_api()
    report = dict(model=settings.model, commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  rounds=ROUNDS, attempts=[])
    draft = PlanningDraft(conditions=PlanningConditions(event_type='MT', headcount=30))
    n = 0
    for round_index in range(ROUNDS):
        for label, text in CASES.items():
            n += 1
            request = PlanningChatRequest(request_id=f'measure-{n}', club_id='synthetic-club', event_id='synthetic-event',
                                          conversation_id=f'synthetic-{n}', base_revision=0, draft=draft, resume_state=None,
                                          reference_date='2026-11-04',
                                          message=PlanningUserMessage(id=f'user-{n}', content=text))
            clock['events'] = []
            clock['t0'] = time.perf_counter()
            try:
                await chat_planning(request, progress=Port())
                error = None
            except Exception as cause:
                error = type(cause).__name__
            mark('end')
            report['attempts'].append(dict(case=label, round=round_index + 1, error=error, events=clock['events']))
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(label, round_index + 1, error or 'ok', flush=True)


asyncio.run(main(Path(sys.argv[1])))
