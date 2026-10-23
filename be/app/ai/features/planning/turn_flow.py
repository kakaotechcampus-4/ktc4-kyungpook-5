"""5-2 실행 준비: 조건 추출 → 조회 판단 → 검색. 답변과 질문 상태는 5-3에서 조립한다."""

from pydantic import model_validator

from ...contracts import ContractModel
from ...errors import AIInvalidResponseError, AIRetryableError, AITimeoutError
from ...llm import aembed_texts, ainvoke_structured
from ...ports import RecordSearchPort
from ..retrieval.indexing import Embed
from ..retrieval.nodes import Invoke
from .lookup import LOOKUP_PROMPT_VERSION, LookupDecider, RecordLookupDecision, call_lookup_model, decide_record_lookup
from .nodes import Extractor, call_extraction_model, extract_condition_changes
from .records import search_planning_records
from .schemas import ConditionExtractionResult, PlanningRecordSearchInput
from .turn_schemas import PlanningTurnInput, RecordLookupState


class PlanningTurnPreparation(ContractModel):
    extraction: ConditionExtractionResult
    lookup_decision: RecordLookupDecision
    record_lookup: RecordLookupState
    lookup_prompt_version: str = LOOKUP_PROMPT_VERSION

    @model_validator(mode="after")
    def _consistent(self):
        allowed = {"SKIP": {"SKIPPED"}, "CLARIFY": {"NEEDS_CLARIFICATION"},
                   "SEARCH": {"SUCCEEDED", "FAILED"}}
        if self.record_lookup.status not in allowed[self.lookup_decision.action]:
            raise ValueError("조회 판단과 실행 결과가 일치해야 합니다")
        found = self.record_lookup.result
        extraction = self.extraction
        if found and (found.planning_event_id, found.request_id, found.base_version) != (
            extraction.event_id, extraction.request_id, extraction.base_version,
        ):
            raise ValueError("다른 행사·요청·버전의 검색 결과입니다")
        return self


async def prepare_planning_turn(
    request: PlanningTurnInput, *, port: RecordSearchPort,
    extract: Extractor = call_extraction_model,
    decide: LookupDecider = call_lookup_model,
    embed: Embed = aembed_texts, invoke: Invoke = ainvoke_structured,
) -> PlanningTurnPreparation:
    """조건·조회 판단 실패는 전파하고 검색만의 일시적 실패는 상태로 반환한다."""
    source = request.extraction_input
    extraction = await extract_condition_changes(source, extract=extract)
    if (extraction.event_id, extraction.request_id, extraction.base_version) != (
        source.event_id, source.request_id, source.base_version,
    ):
        raise AIInvalidResponseError("조건 추출의 요청 식별 정보가 다릅니다")
    decision = await decide_record_lookup(source, extraction.candidate_conditions, invoke=decide)
    if decision.action == "SKIP":
        lookup = RecordLookupState(status="SKIPPED")
    elif decision.action == "CLARIFY":
        lookup = RecordLookupState(status="NEEDS_CLARIFICATION", clarification=decision.clarification)
    else:
        search_request = PlanningRecordSearchInput(
            club_id=request.club_id, planning_event_id=source.event_id,
            request_id=source.request_id, base_version=source.base_version,
            query=decision.query, reference_date=source.reference_date,
            conditions=extraction.candidate_conditions,
        )
        try:
            result = await search_planning_records(search_request, port=port, embed=embed, invoke=invoke)
        except AITimeoutError:
            lookup = RecordLookupState(status="FAILED", error_code="TIMEOUT")
        except AIInvalidResponseError:
            lookup = RecordLookupState(status="FAILED", error_code="INVALID_RESPONSE")
        except AIRetryableError:
            lookup = RecordLookupState(status="FAILED", error_code="RETRYABLE")
        else:
            lookup = RecordLookupState(status="SUCCEEDED", result=result)
    return PlanningTurnPreparation(extraction=extraction, lookup_decision=decision, record_lookup=lookup)
