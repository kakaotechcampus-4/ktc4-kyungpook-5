"""#205: 첫 비교에서 드러난 모호함과 구분해 명확한 재개/새 표현을 추가 확인한다."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from app.ai.scripts import check_planning_deferrals as evaluation
from app.ai.scripts.measure_planning_latency import write_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    cases = (
        evaluation.Case('generation_holdout',
            '초안 작업은 다음에 하자. 지금은 예상 인원만 60명으로 기록해 줘.'),
        evaluation.Case('explicit_resume',
            '날짜 보류를 해제하고 지금부터 일정을 정하자. 인원은 60명으로 바꾸고 초안 생성은 하지 마.',
            initial_topics=('dates',)),
    )
    # 입력만 별도 집합으로 바꾼다. 첫 90요청과 프롬프트/모델/실행 코드는 같다.
    with patch.object(evaluation, 'CASES', cases):
        report = asyncio.run(evaluation.run(args.output_dir,
            baseline_ref='a60e8184c3ed17a9d688c4b2b040fb01307c4bce', repeats=3, controls=3))
    report['followup_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['purpose'] = 'Separate follow-up; original ambiguous date_resume remains scored as measured'
    write_manifest(args.output_dir, report)
    print(json.dumps(report['groups'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
