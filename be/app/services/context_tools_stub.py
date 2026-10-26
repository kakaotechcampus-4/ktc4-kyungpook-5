"""Jev 판단 뒤 쓰는 도구와 Discord 맥락 판단의 더미 구현.

실제 기록 검색(임베딩, #72)·LLM 생성(#124)·Discord 할 일 도출(#116)이 BE에 연결되기
전까지 curl 흐름을 끝까지 확인하기 위한 자리다. 모두 결정론적이며 외부 호출이 없다.
실제 구현이 생기면 이 모듈의 함수만 교체한다.

- search_records: 동아리 기록의 parse_result 블록을 글자 2-gram 겹침으로 찾는다.
  검색된 블록만 출처로 돌려준다 — 없는 회칙을 만들어내지 않는다.
- generate_text: 생성 모델 대신 요청 문장을 그대로 담은 더미 문구를 돌려준다.
- judge_discord_window / draft_task: 최근 메시지에 "~해야" 같은 해야 할 일 표현이
  있으면 할 일 후보를 만든다.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import JudgeRoute, RecordCategory, RecordParseStatus
from app.models.records import Record

STUB_TOOLS_VERSION = "stub-tools-v1"

# 검색 결과로 인정하는 최소 겹침 수. 조사만 겹치는 우연한 일치를 거른다.
_MIN_SHARED_BIGRAMS = 4
_SEARCH_LIMIT = 3


@dataclass
class RecordHit:
    record_id: str
    file_name: str
    location_label: str
    text: str
    score: int


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


async def search_records(
    session: AsyncSession, *, club_id: str, query: str
) -> list[RecordHit]:
    query_grams = _bigrams(query)
    records = await session.scalars(
        select(Record).where(
            Record.club_id == club_id,
            # 확정 전 영수증 원본은 검색 대상이 아니다(#133).
            Record.category != RecordCategory.RECEIPT,
            Record.parse_status.in_(
                (RecordParseStatus.COMPLETED, RecordParseStatus.INDEXED)
            ),
        )
    )
    hits: list[RecordHit] = []
    for record in records:
        for block in (record.parse_result or {}).get("blocks", []):
            score = len(query_grams & _bigrams(block["text"]))
            if score >= _MIN_SHARED_BIGRAMS:
                hits.append(
                    RecordHit(
                        record_id=record.id,
                        file_name=record.file_name,
                        location_label=block["location"]["label"],
                        text=block["text"],
                        score=score,
                    )
                )
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:_SEARCH_LIMIT]


def answer_from_hits(hits: list[RecordHit]) -> str:
    """검색한 원문을 그대로 인용한다. 생성 모델로 요약하지 않는다."""
    top = hits[0]
    return f"{top.file_name} {top.location_label}: {top.text}"


def generate_text(request: str) -> str:
    return f"(더미 생성) 요청 문장: {request.strip()}"


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
