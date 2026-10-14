"""회의 판단의 입력 구성과 요청·결과 검증을 확인한다.

입력 형식은 검색어 측정(#123)과 같아야 측정값을 기준선으로 쓸 수 있다.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import get_args

import pytest
from pydantic import ValidationError

from app.ai.contracts import RecordSource, SourceLocation
from app.ai.features.meeting.context import (
    MEETING_CONTEXT_UTTERANCES,
    PROMPT_VERSION,
    build_judge_input,
    build_judge_messages,
    judge_system_prompt,
)
from app.ai.features.meeting.schemas import (
    JudgeOutput,
    JudgeTrace,
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingEvent,
    MeetingUtterance,
    ReasonCode,
)

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

# 프롬프트 원문을 바꾸면 이 값이 달라져 테스트가 실패한다.
# 바꿀 때는 PROMPT_VERSION을 올리고 다시 잰 뒤, 새 버전과 해시를 여기에 더한다.
PROMPT_SHA256 = {
    "meeting-judge-v4": "b99262f3c101c62616b92c5d915b33ca12ef92e26619cc7eeb26ab5cff9c03e7",
}

SOURCE = RecordSource(
    record_id="rec_mt_2025", file_name="2025 봄 MT 결과보고", location=SourceLocation(label="2쪽 · 2. 예산")
)
TRACE = JudgeTrace(model="gpt-5.6-luna", prompt_version=PROMPT_VERSION, judge_ms=1480)


def _utterance(seq: int, text: str = "작년 MT 숙소비 얼마였지?", at: datetime | None = None):
    at = at or datetime(2026, 3, 5, 14, 0, tzinfo=KST)
    return MeetingUtterance(
        utterance_id=f"u-{seq}", seq=seq, text=text, started_at=at, ended_at=at + timedelta(seconds=2)
    )


def _request(utterance=None, context=(), event=None):
    return JudgeUtteranceRequest(
        meeting_id="mtg_1",
        club_id="clb_keunnamu",
        utterance=utterance or _utterance(10),
        context=context,
        event=event,
    )


# --- 입력 구성 ---------------------------------------------------------------


def test_입력은_측정_때와_같은_형식이다():
    context = (_utterance(8, "작년 봄 MT 얘기부터 하죠"), _utterance(9, "가평 펜션이었죠"))

    text = build_judge_input(_request(_utterance(10, "그때 숙소비 얼마였지?"), context))

    assert text == (
        "[회의 날짜]\n2026-03-05\n\n"
        "[최근 대화]\n작년 봄 MT 얘기부터 하죠\n가평 펜션이었죠\n\n"
        "[방금 발화]\n그때 숙소비 얼마였지?"
    )


def test_회의_날짜는_한국_날짜로_바꾼다():
    # UTC 3월 4일 23시는 한국 3월 5일 오전 8시다
    late = _utterance(1, at=datetime(2026, 3, 4, 23, 0, tzinfo=UTC))

    assert build_judge_input(_request(late)).startswith("[회의 날짜]\n2026-03-05\n")


def test_앞_발화는_마지막_네_개만_쓴다():
    context = tuple(_utterance(seq, f"앞 발화 {seq}") for seq in range(1, 7))

    text = build_judge_input(_request(_utterance(7), context))

    assert MEETING_CONTEXT_UTTERANCES == 4
    assert "앞 발화 2" not in text
    assert "[최근 대화]\n앞 발화 3\n앞 발화 4\n앞 발화 5\n앞 발화 6\n\n" in text


def test_앞_발화가_없으면_없음으로_적는다():
    assert "[최근 대화]\n(없음)\n\n" in build_judge_input(_request())


def test_행사가_있을_때만_행사_칸을_넣는다():
    event = MeetingEvent(event_id="evt_mt", title="2026 봄 MT")

    with_event = build_judge_input(_request(event=event))

    assert "[회의 날짜]\n2026-03-05\n\n[행사]\n2026 봄 MT\n\n[최근 대화]" in with_event
    assert "[행사]" not in build_judge_input(_request())


def test_지시문과_입력을_메시지_두_개로_보낸다():
    messages = build_judge_messages(_request())

    assert [message.type for message in messages] == ["system", "human"]
    assert messages[0].content == judge_system_prompt()


def test_프롬프트를_바꾸면_버전도_올린다():
    digest = hashlib.sha256((judge_system_prompt() + "\n").encode("utf-8")).hexdigest()

    assert PROMPT_SHA256.get(PROMPT_VERSION) == digest


def test_조회하지_않은_이유_코드는_프롬프트의_경우와_하나씩_맞는다():
    # 모델이 보는 기준과 사람이 검수하는 기준이 같아야 한다(#117).
    # 프롬프트에 경우를 더하면 ReasonCode에도 더한다
    prompt = judge_system_prompt()
    section = prompt.split("조회가 필요 없는 경우:\n", 1)[1].split("\n\n", 1)[0]
    cases = [line for line in section.splitlines() if line.startswith("- ")]

    codes = get_args(ReasonCode)
    assert len(cases) == codes.index("NEEDS_CONTEXT")
    assert codes[-2:] == ("NEEDS_CONTEXT", "OTHER")


def test_출력_스키마에는_모델에_보낼_설명이_없다():
    # 클래스 설명은 description으로 모델 입력에 들어가 측정 때와 달라진다
    schema = JudgeOutput.model_json_schema()

    assert "description" not in schema
    assert schema["required"] == ["needs_lookup", "query"]


# --- 요청 검증 ---------------------------------------------------------------


def test_시간대_없는_발화_시각은_받지_않는다():
    with pytest.raises(ValidationError, match="timezone"):
        _utterance(1, at=datetime(2026, 3, 5, 14, 0))


def test_빈_전사는_받지_않는다():
    with pytest.raises(ValidationError):
        _utterance(1, text="   ")


def test_발화_끝이_시작보다_앞서면_받지_않는다():
    at = datetime(2026, 3, 5, 14, 0, tzinfo=KST)

    with pytest.raises(ValidationError, match="끝 시각"):
        MeetingUtterance(
            utterance_id="u-1", seq=1, text="회비 얼마였지?", started_at=at, ended_at=at - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    ("context_seqs", "seq"),
    [((2, 1), 3), ((1, 3), 3), ((4,), 3)],
    ids=["앞 발화 순서가 뒤바뀜", "앞 발화가 이번 발화와 같은 순번", "앞 발화가 이번 발화보다 뒤"],
)
def test_앞_발화_순서가_맞지_않으면_받지_않는다(context_seqs, seq):
    with pytest.raises(ValidationError, match="순번 순서"):
        _request(_utterance(seq), tuple(_utterance(item) for item in context_seqs))


# --- 결과 검증 ---------------------------------------------------------------


def _result(**fields):
    base = {"utterance_id": "u-10", "source_version": 1, "trace": TRACE}
    return JudgeUtteranceResult(**base | fields)


def test_결과_종류마다_필요한_값이_있으면_통과한다():
    assert _result(route="NONE", kind="NO_LOOKUP").kind == "NO_LOOKUP"
    assert _result(route="RAG", kind="NOT_FOUND", question="2024 신환회 장소").kind == "NOT_FOUND"
    answered = _result(
        route="RAG", kind="ANSWER", question="2025 봄 MT 숙소비", answer="550,000원", sources=(SOURCE,)
    )
    assert answered.sources == (SOURCE,)


@pytest.mark.parametrize(
    "fields",
    [
        {"route": "RAG", "kind": "NO_LOOKUP"},
        {"route": "NONE", "kind": "NO_LOOKUP", "question": "회비"},
        {"route": "NONE", "kind": "ANSWER", "question": "회비", "answer": "2만 원", "sources": (SOURCE,)},
        {"route": "RAG", "kind": "ANSWER", "question": "회비", "answer": "2만 원"},
        {"route": "RAG", "kind": "ANSWER", "answer": "2만 원", "sources": (SOURCE,)},
        {"route": "RAG", "kind": "NOT_FOUND", "question": "회비", "answer": "2만 원"},
        {"route": "RAG", "kind": "NOT_FOUND", "question": "  "},
    ],
    ids=[
        "조회 안 함인데 RAG",
        "조회 안 함인데 질문이 있음",
        "답인데 NONE",
        "출처 없는 답",
        "질문 없는 답",
        "기록 없음인데 답이 있음",
        "빈 질문",
    ],
)
def test_결과_종류와_값이_맞지_않으면_받지_않는다(fields):
    with pytest.raises(ValidationError):
        _result(**fields)
