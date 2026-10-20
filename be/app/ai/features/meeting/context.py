"""판단 모델에 보낼 입력을 만든다.

입력 형식은 검색어 측정(#123)에서 v4 프롬프트와 함께 잰 형식과 같다.
바꾸면 측정값과 비교할 수 없으므로 PROMPT_VERSION을 올리고 다시 잰다.
"""

from datetime import date
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .schemas import JudgeUtteranceRequest

# 판단에 함께 넘길 앞 발화 수. BE는 이 값만큼 실어 보낸다(#113).
# 2개로는 3~4발화 전에만 나온 주제가 검색어에서 빠졌다(#123).
MEETING_CONTEXT_UTTERANCES = 4

# prompts/judge.md를 바꾸면 올린다. 판단 기록(trace)에 남아 바뀌기 전후를 나눠 본다
PROMPT_VERSION = "meeting-judge-v5"

# prompts/query.md를 바꾸면 올린다. 판단 전용 모델(Laya)이 조회로 본 발화에 검색어만 받는 지시문이다(#117)
QUERY_PROMPT_VERSION = "meeting-query-v1"

# "작년"을 연도로 풀 때 쓰는 회의 날짜의 기준. 발화 시각은 UTC로 올 수 있다
MEETING_TIMEZONE = ZoneInfo("Asia/Seoul")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"
_QUERY_PROMPT_PATH = Path(__file__).parent / "prompts" / "query.md"


@cache
def judge_system_prompt() -> str:
    """판단 지시문 원문. 파일 끝 줄바꿈은 측정 때 문자열에 없어 뺀다"""
    return _PROMPT_PATH.read_text(encoding="utf-8").removesuffix("\n")


@cache
def query_system_prompt() -> str:
    """검색어만 받는 지시문 원문. 검색어 규칙은 judge.md의 검색어 부분과 같다"""
    return _QUERY_PROMPT_PATH.read_text(encoding="utf-8").removesuffix("\n")


def meeting_date(request: JudgeUtteranceRequest) -> date:
    """회의 날짜. "작년"을 연도로 풀 때와 기록 검색의 기준일로 같이 쓴다"""
    return request.utterance.started_at.astimezone(MEETING_TIMEZONE).date()


def build_judge_messages(request: JudgeUtteranceRequest) -> list[BaseMessage]:
    """지시문과 이번 발화 입력을 모델에 보낼 메시지로 만든다"""
    return [
        SystemMessage(judge_system_prompt()),
        HumanMessage(build_judge_input(request)),
    ]


def build_query_messages(request: JudgeUtteranceRequest) -> list[BaseMessage]:
    """검색어만 받는 메시지. 입력 글은 판단과 같다. 같은 입력이어야 검색어 측정값이 이어진다"""
    return [
        SystemMessage(query_system_prompt()),
        HumanMessage(build_judge_input(request)),
    ]


def build_judge_input(request: JudgeUtteranceRequest) -> str:
    """판단 입력 글.

    [회의 날짜]
    2026-03-05

    [행사]            ← 회의를 행사에 묶었을 때만
    2026 봄 MT

    [최근 대화]
    (앞 발화 최대 4개, 오래된 것부터. 없으면 "(없음)")

    [방금 발화]
    그때 숙소비 얼마였지?
    """
    recent = request.context[-MEETING_CONTEXT_UTTERANCES:]

    parts = [f"[회의 날짜]\n{meeting_date(request).isoformat()}"]
    if request.event is not None:
        parts.append(f"[행사]\n{request.event.title}")
    parts.append(
        "[최근 대화]\n" + ("\n".join(item.text for item in recent) if recent else "(없음)")
    )
    parts.append(f"[방금 발화]\n{request.utterance.text}")
    return "\n\n".join(parts)
