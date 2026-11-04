"""#269 후속: eval_planning_agent를 v7/v8 메시지 순서로 번갈아 돌린다(실제 모델 호출).

요청마다 nodes.agent_messages를 비교 실행기의 v7/v8 함수로 바꿔 끼운다. 결과 JSON의 prompt_version은
모듈 상수라 v7 실행도 planning-agent-v8로 적히므로 파일 이름의 v7/v8로 구분한다. be/에서 실행한다.
  PYTHONPATH=. .venv/bin/python app/ai/docs/planning/evaluation-results/planning-agent-context-layout-2026-11-04/agent-eval/run_layouts.py <작업 트리 밖 폴더>
"""
import asyncio, sys
from pathlib import Path
from unittest.mock import patch
from app.ai.features.planning.agent import nodes
from app.ai.scripts import eval_planning_agent as ev
from app.ai.scripts.compare_agent_context_layout import LAYOUTS

OUT = Path(sys.argv[1])
RECORDS = ev.AI_DIR / 'tests/fixtures/eval/planning_agent_records.json'

async def main():
    plan = [('basic', i, v) for i in (1, 2, 3) for v in (('v7', 'v8') if i % 2 else ('v8', 'v7'))]
    plan += [('records', 1, 'v7'), ('records', 1, 'v8')]
    for kind, i, variant in plan:
        path = OUT / f'{kind}-{i}-{variant}.json'
        with patch.object(nodes, 'agent_messages', LAYOUTS[variant]):
            if kind == 'basic':
                code = await ev.run(path)
            else:
                code = await ev.run(path, cases=RECORDS, with_records=True)
        print('DONE', kind, i, variant, 'exit', code, flush=True)
        await asyncio.sleep(1)

asyncio.run(main())
