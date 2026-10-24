"""검색 Tool의 얇은 어댑터. 기존 retrieval을 재사용하고 현재 초안은 바꾸지 않는다."""

from datetime import date
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from ....contracts import ContractModel, EventConditions, NonBlankStr
from ....errors import AIRetryableError
from ....llm import aembed_texts, ainvoke_structured
from ....ports import RecordSearchPort
from ...retrieval.indexing import Embed
from ...retrieval.nodes import Invoke, search_records
from ...retrieval.schemas import RecordSearchRequest, RecordSearchResult
from .state import PlanningDraft


class SearchPastEventsInput(ContractModel):
    query: Annotated[NonBlankStr, Field(max_length=4000)]


class RecordLookupResult(ContractModel):
    status: Literal["available", "not_found", "failed", "rejected"]
    query: str | None = None
    result: RecordSearchResult | None = None
    reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status in {"available", "not_found"}:
            if self.result is None or not self.query:
                raise ValueError("검색 성공에는 질문과 검색 결과가 필요합니다")
            found = bool(self.result.facts or self.result.conflicts)
            if found != (self.status == "available"):
                raise ValueError("검색 상태와 근거 유무가 다릅니다")
        elif self.result is not None or self.reason is None:
            raise ValueError("검색 실패·거절에는 근거 대신 이유가 필요합니다")
        return self


class RecordSearcher(Protocol):
    async def __call__(self, arguments: SearchPastEventsInput, draft: PlanningDraft,
                       reference_date: date) -> RecordLookupResult: ...


async def search_past_events(
    arguments: SearchPastEventsInput, draft: PlanningDraft, reference_date: date,
    *, club_id: str, port: RecordSearchPort, embed: Embed = aembed_texts, invoke: Invoke = ainvoke_structured,
) -> RecordLookupResult:
    """질문만 모델에서 받고, 검색 범위·저장소는 호출자가 제공한다."""
    conditions = draft.conditions
    context = EventConditions(event_type=conditions.event_type, start_date=conditions.start_date)
    request = RecordSearchRequest(
        club_id=club_id, query=arguments.query, today=reference_date,
        conditions=context if conditions.event_type is not None or conditions.start_date is not None else None,
        # 현재 계획 행사로 필터링하면 과거 자료가 제외된다. 올해 장소·금액도 필터로 쓰지 않는다.
        event_id=None, category=None, limit=5,
    )
    try:
        result = await search_records(request, port=port, embed=embed, invoke=invoke, rewrite=True, max_rounds=1)
    except AIRetryableError:
        # 검색 실패는 기록 없음이 아니다. 이미 적용한 조건을 유지한 채 LLM에 실패를 전달한다.
        return RecordLookupResult(status="failed", query=arguments.query,
                                  reason="과거 기록 조회에 실패해 내용을 확인하지 못했어요.")
    return RecordLookupResult(
        status="available" if result.facts or result.conflicts else "not_found",
        query=arguments.query, result=result,
    )
