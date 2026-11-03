"""실제 모델로 토리 조회 대상 회귀 사례를 점검한다. 비밀·설정값은 출력하지 않는다."""
import asyncio
import json
from pathlib import Path

from app.ai import ToriIntentRequest, classify_tori_intent


async def main():
    cases = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/eval/tori_targets.json').read_text())
    failed = 0
    for case in cases:
        try:
            result = await classify_tori_intent(ToriIntentRequest(message=case['message'], reference_date='2026-10-30'))
            actual = result.model_dump(mode='json')
            ok = all(actual[key] == value for key, value in case.items() if key != 'message')
            print(f"{case['message']}: {'PASS' if ok else 'FAIL'} ({actual['intent']})", flush=True)
            failed += not ok
        except Exception as error:
            print(f"{case['message']}: ERROR ({type(error).__name__})", flush=True)
            failed += 1
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
