"""기록 검색 평가 질문을 회의 발화로 보고, 회의 판단이 만드는 검색어를 파일로 남긴다 (#72, #114).

키가 필요해 CI에서 돌리지 않는다. 회의 어시스턴트는 판단이 만든 검색어로 기록을 찾으므로,
평가 질문 원문이 아니라 이 검색어로 기록 검색을 재야 회의에서의 값이 나온다.

    cd be && uv run python app/ai/scripts/make_meeting_queries.py [--out 검색어.json]
    cd be && uv run python app/ai/scripts/eval_retrieval.py --search records --no-rewrite \\
        --queries 검색어.json --holdout --no-cache

질문마다 앞 발화와 행사 없이, 질문의 기준일을 회의 날짜로 둔 발화 하나로 판단한다(판단 프롬프트·모델은 회의와 같다).
판단이 조회가 필요 없다고 보면 검색어는 null이다. 회의에서는 그 발화에 아무것도 띄우지 않는다.
판단 응답은 실행마다 조금씩 다를 수 있어, 측정에 쓴 파일을 결과와 함께 남긴다.
AI_* 는 be/.env 에서 읽는다. 키는 출력하지 않는다.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from datetime import time as clock
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import get_settings
from app.ai.features.meeting.context import (
    MEETING_TIMEZONE,
    PROMPT_VERSION,
    build_judge_messages,
)
from app.ai.features.meeting.nodes import call_judge_model
from app.ai.features.meeting.schemas import JudgeUtteranceRequest, MeetingUtterance
from app.ai.scripts.eval_retrieval import CLUB_ID, QUESTIONS, _git


def _request(question: dict) -> JudgeUtteranceRequest:
    # 평가 질문에는 발화 시각이 없어 기준일 오후 2시에 한 말로 둔다
    at = datetime.combine(
        datetime.fromisoformat(question["today"]).date(), clock(14, 0), MEETING_TIMEZONE
    )
    return JudgeUtteranceRequest(
        meeting_id="eval",
        club_id=CLUB_ID,
        utterance=MeetingUtterance(
            utterance_id=question["id"], seq=1, text=question["question"], started_at=at, ended_at=at
        ),
    )


async def run() -> dict:
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    queries = {}
    for question in questions:
        started = time.perf_counter()
        output = await call_judge_model(build_judge_messages(_request(question)))
        query = output.query.strip() if output.needs_lookup else None
        queries[question["id"]] = {
            "question": question["question"],
            "query": query or None,
            "judge_ms": int((time.perf_counter() - started) * 1000),
        }
        print(f"- {question['id']} {question['question']} → {query or '(조회 아님)'}")
    return {
        "settings": {
            **_git(),
            "model": get_settings().model,
            "prompt_version": PROMPT_VERSION,
            "generated_at": datetime.now(MEETING_TIMEZONE).isoformat(timespec="seconds"),
        },
        "queries": queries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="검색어를 저장할 경로")
    args = parser.parse_args()

    result = asyncio.run(run())
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    skipped = sum(1 for item in result["queries"].values() if item["query"] is None)
    print(f"조회 아님 {skipped}개. 저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
