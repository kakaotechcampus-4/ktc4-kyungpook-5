"""Discord 맥락 판단의 더미 구현.

Discord 할 일 도출(#116)이 BE에 연결되기 전까지 curl 흐름을 끝까지 확인하기 위한
자리다. 결정론적이며 외부 호출이 없다. 회의 발화 검색·생성은 #141에서
app.ai.judge_utterance로 이미 바뀌었다 — 그쪽 더미(search_records/answer_from_hits/
generate_text)는 이 파일에서 지웠다.

- judge_discord_window / draft_task: 최근 메시지에 "~해야" 같은 해야 할 일 표현이
  있으면 할 일 후보를 만든다.
"""

import re

from app.core.enums import JudgeRoute

STUB_TOOLS_VERSION = "stub-tools-v1"

_TODO_PATTERN = re.compile(r"(해야|확인해 ?주|준비해 ?주|부탁)")


def judge_discord_window(latest_text: str) -> tuple[JudgeRoute, str]:
    """(route, 판단 이유). 할 일 도출은 LLM 분기의 도구로 본다."""
    if _TODO_PATTERN.search(latest_text):
        return JudgeRoute.LLM, "대화에서 해야 할 일이 보입니다."
    return JudgeRoute.NONE, "할 일로 볼 내용이 없습니다."


def draft_task(latest_text: str, context_texts: list[str]) -> tuple[str, str]:
    """(title, description). 해야 할 일 표현 바로 앞 세 단어로 제목을 만든다."""
    match = _TODO_PATTERN.search(latest_text)
    before = latest_text[: match.start()] if match else latest_text
    words = before.split()[-3:]
    title = f"{' '.join(words)}하기" if words else latest_text.strip()
    description = "대화 맥락: " + " / ".join(text.strip() for text in context_texts)
    return title, description
