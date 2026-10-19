"""판단 뒤 기록을 찾아 답을 쓰는 단계(RecordLookup)의 실제 구현.

기록 검색은 retrieval의 find_chunks, 근거 판단은 assess_chunks를 그대로 쓴다(#72).
search_records(rewrite=False)와 같은 단계라 기록 검색의 측정값과 규칙이 회의에도 그대로 맞다.
이 파일이 더하는 것은 근거 판단 결과를 회의 카드 한 장의 문구와 출처로 옮기는 일뿐이다.
"""

from ...llm import aembed_texts, ainvoke_structured
from ...ports import RecordSearchPort, RetrievedChunk
from ..retrieval.indexing import Embed
from ..retrieval.nodes import (
    ASSESS_EVIDENCE_PROMPT_VERSION,
    Invoke,
    assess_chunks,
    find_chunks,
)
from ..retrieval.schemas import RecordFact, RecordSearchRequest, RecordSearchResult
from .schemas import MeetingAnswer


class RecordsLookup:
    """`RecordLookup` 구현. 검색할 기록은 BE가 주입한 port에서 찾는다.

    테스트에서는 `embed`와 `invoke`를 가짜로 바꾼다.
    """

    answer_prompt_version = ASSESS_EVIDENCE_PROMPT_VERSION

    def __init__(
        self,
        records: RecordSearchPort,
        *,
        embed: Embed = aembed_texts,
        invoke: Invoke = ainvoke_structured,
    ) -> None:
        self._records = records
        self._embed = embed
        self._invoke = invoke

    async def search(self, request: RecordSearchRequest) -> tuple[RetrievedChunk, ...]:
        return await find_chunks(request, port=self._records, embed=self._embed)

    async def answer(
        self, request: RecordSearchRequest, chunks: tuple[RetrievedChunk, ...]
    ) -> MeetingAnswer | None:
        result = await assess_chunks(request, chunks, invoke=self._invoke)
        return to_meeting_answer(result)


def to_meeting_answer(result: RecordSearchResult) -> MeetingAnswer | None:
    """근거 판단 결과를 회의 카드의 답으로 옮긴다. 확인한 것이 없으면 None("기록에 없음")이다.

    모델을 다시 부르지 않고 결과의 문구를 그대로 옮긴다. 한 줄에 하나씩 둔다.

        사실        2025 봄 MT 숙박비 550,000원
        자료 간 차이 2025 봄 MT 참가 인원: 28명 (2025 봄 MT 결과보고.pdf) / 27명 (2025 상반기 장부.xlsx)
        확인 못 함  기록에 없음: 숙소비 세부 내역

    자료 간 차이는 하나를 고르지 않고 값마다 문서 이름을 붙인다(AI-RET-03).
    확인하지 못한 것은 확인한 것이 있을 때만 덧붙인다. 그것뿐이면 NOT_FOUND로 보인다.
    """
    lines = [fact.content for fact in result.facts]
    lines += [
        f"{conflict.description}: "
        + " / ".join(_with_file_names(value) for value in conflict.values)
        for conflict in result.conflicts
    ]
    if not lines:
        return None
    if result.not_found:
        lines.append(f"기록에 없음: {', '.join(result.not_found)}")

    facts = [*result.facts, *(value for conflict in result.conflicts for value in conflict.values)]
    # 같은 출처는 한 번만, 결과에 나온 순서대로 둔다
    sources = dict.fromkeys(source for fact in facts for source in fact.sources)
    return MeetingAnswer(answer="\n".join(lines), sources=tuple(sources))


def _with_file_names(value: RecordFact) -> str:
    names = dict.fromkeys(source.file_name for source in value.sources)
    return f"{value.content} ({', '.join(names)})"
