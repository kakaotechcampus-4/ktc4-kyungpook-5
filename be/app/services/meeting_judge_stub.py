"""회의 발화 판단의 더미 구현 (#135).

실제 `app.ai.judge_utterance`는 아직 공개 facade에 없다(#114 미완료). 이 함수는
그 호출을 흉내내는 자리이며, 나중에 실제 AI 함수가 공개되면 이 모듈을 그 호출로
바꾸기만 하면 된다 — 호출부(services/meeting_service.py)의 입출력 모양은
AI가 초안으로 정의해둔 JudgeUtteranceRequest/Result(#114)를 그대로 따른다.

판단 규칙은 결정론적인 더미다: 물음표가 있으면 RAG(검색 필요)로, 없으면 NONE으로
본다. 실제 검색 백엔드가 아직 없어 RAG여도 항상 NOT_FOUND를 돌려준다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import JudgeKind, JudgeRoute

STUB_MODEL_NAME = "stub-meeting-judge"
STUB_PROMPT_VERSION = "stub-v1"


@dataclass
class JudgeResult:
    route: JudgeRoute
    kind: JudgeKind
    question: str | None
    answer: str | None
    sources: list[dict[str, Any]]
    trace: dict[str, Any] = field(default_factory=dict)


def judge_utterance_stub(text: str) -> JudgeResult:
    needs_lookup = "?" in text or "？" in text

    if not needs_lookup:
        return JudgeResult(
            route=JudgeRoute.NONE,
            kind=JudgeKind.NO_LOOKUP,
            question=None,
            answer=None,
            sources=[],
            trace={
                "model": STUB_MODEL_NAME,
                "promptVersion": STUB_PROMPT_VERSION,
                "judgeMs": 0,
                "toolCalls": [],
            },
        )

    # 실제 기록 검색(#72)이 아직 연결되지 않아 항상 NOT_FOUND다.
    return JudgeResult(
        route=JudgeRoute.RAG,
        kind=JudgeKind.NOT_FOUND,
        question=text.strip(),
        answer=None,
        sources=[],
        trace={
            "model": STUB_MODEL_NAME,
            "promptVersion": STUB_PROMPT_VERSION,
            "judgeMs": 0,
            "toolCalls": [
                {
                    "tool": "records.search",
                    "input": text.strip(),
                    "status": "OK",
                    "durationMs": 0,
                    "resultCount": 0,
                }
            ],
        },
    )
