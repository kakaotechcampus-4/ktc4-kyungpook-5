"""회의 발화 판단의 더미 구현 (#135).

실제 `app.ai.judge_utterance`는 아직 공개 facade에 없다(#114 미완료). 이 함수는
그 호출을 흉내내는 자리이며, 나중에 실제 AI 함수가 공개되면 이 모듈을 그 호출로
바꾸기만 하면 된다. 판단 뒤 검색·생성은 services/context_tools_stub.py가 맡는다.

판단 규칙은 결정론적인 더미다. 입력으로 분기를 지정하지 않고 문장만 본다.
- 물음표가 있으면 기록을 찾아봐야 하는 질문으로 보고 RAG
- "바꿔/써/만들어/정리해/요약해 주세요" 같은 요청이면 LLM
- 나머지는 NONE
"""

from dataclasses import dataclass

from app.core.enums import JudgeRoute

STUB_MODEL_NAME = "stub-meeting-judge"
STUB_PROMPT_VERSION = "stub-v2"

_GENERATE_REQUESTS = ("바꿔", "써 줘", "써줘", "써 주", "만들어", "정리해", "요약해", "작성해")


@dataclass
class JudgeResult:
    route: JudgeRoute
    # RAG일 때 검색어. 나머지는 None.
    question: str | None
    # 화면에 보여줄 짧은 판단 이유
    reason: str


def judge_utterance_stub(text: str) -> JudgeResult:
    stripped = text.strip()
    if "?" in stripped or "？" in stripped:
        return JudgeResult(
            route=JudgeRoute.RAG, question=stripped, reason="기록 확인이 필요한 질문입니다."
        )
    if any(word in stripped for word in _GENERATE_REQUESTS):
        return JudgeResult(
            route=JudgeRoute.LLM, question=None, reason="문장 작성 요청입니다."
        )
    return JudgeResult(
        route=JudgeRoute.NONE, question=None, reason="도움이 필요한 발화가 아닙니다."
    )
