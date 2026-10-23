"""계획 입력을 기존 검색에 연결하고 참고 결과를 만든다. 조건 변경·검색 판단은 하지 않는다."""

from ...contracts import EventConditions
from ...llm import aembed_texts, ainvoke_structured
from ...ports import RecordSearchPort
from ..retrieval.indexing import Embed
from ..retrieval.nodes import Invoke, search_records
from ..retrieval.schemas import RecordSearchRequest, RecordSearchResult
from .schemas import PlanningRecordSearchInput, PlanningRecordSearchResult


def build_record_search_request(request: PlanningRecordSearchInput) -> RecordSearchRequest:
    """올해 조건을 검색 필터로 오인하지 않도록 유형·시기만 복사한다."""
    conditions = request.conditions
    context = None
    if conditions.event_type is not None or conditions.start_date is not None:
        context = EventConditions(
            event_type=conditions.event_type,
            start_date=conditions.start_date,
        )
    return RecordSearchRequest(
        club_id=request.club_id,
        query=request.query,
        today=request.reference_date,
        conditions=context,
        # 현재 계획 행사로 자동 제한하면 과거 행사의 기록이 검색되지 않는다.
        event_id=request.target_event_id,
        category=None,
        limit=5,
    )


def build_planning_record_result(
    request: PlanningRecordSearchInput,
    result: RecordSearchResult,
) -> PlanningRecordSearchResult:
    """검색된 사실·출처·미확인·충돌을 손실 없이 옮긴다. 추가 모델 호출은 없다."""
    return PlanningRecordSearchResult(
        planning_event_id=request.planning_event_id,
        request_id=request.request_id,
        base_version=request.base_version,
        status="AVAILABLE" if result.facts or result.conflicts else "NOT_FOUND",
        cards=result.facts,
        not_found=result.not_found,
        conflicts=result.conflicts,
    )


async def search_planning_records(
    request: PlanningRecordSearchInput,
    *,
    port: RecordSearchPort,
    embed: Embed = aembed_texts,
    invoke: Invoke = ainvoke_structured,
) -> PlanningRecordSearchResult:
    """retrieval 결과를 계획 참고 데이터로 반환한다. 호출 실패는 기록 없음으로 바꾸지 않는다.

    검색 의도와 접근 범위는 호출자가 결정한다. 외부 재검색 루프를 추가하지 않으며,
    한 회차 안의 검색어 정리·근거 판단은 기존 retrieval이 수행한다.
    """
    result = await search_records(
        build_record_search_request(request),
        port=port,
        embed=embed,
        invoke=invoke,
        rewrite=True,
        max_rounds=1,
    )
    return build_planning_record_result(request, result)
