"""조회 필요 판단. 출력 형식·현재 발화 근거를 검사하며 검색 자체는 하지 않는다."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import Field, model_validator

from ...contracts import ContractModel, NonBlankStr
from ...errors import AIInvalidResponseError
from ...llm import ainvoke_structured
from .schemas import ConditionExtractionInput, MessageEvidence, PlanningConditions

LOOKUP_PROMPT_VERSION = "planning-lookup-v1"


class RecordLookupDecision(ContractModel):
    action: Literal["SKIP", "SEARCH", "CLARIFY"]
    query: Annotated[NonBlankStr, Field(max_length=4000)] | None
    clarification: Annotated[NonBlankStr, Field(max_length=1000)] | None
    evidence: MessageEvidence

    @model_validator(mode="after")
    def _payload_for_action(self):
        if (self.query is not None, self.clarification is not None) != {
            "SKIP": (False, False), "SEARCH": (True, False), "CLARIFY": (False, True),
        }[self.action]:
            raise ValueError("조회 행동과 검색어·확인 질문이 일치해야 합니다")
        return self


LookupDecider = Callable[[list[BaseMessage]], Awaitable[RecordLookupDecision]]


async def call_lookup_model(messages: list[BaseMessage]) -> RecordLookupDecision:
    return await ainvoke_structured(messages, RecordLookupDecision)


async def decide_record_lookup(
    request: ConditionExtractionInput, conditions: PlanningConditions, *,
    invoke: LookupDecider = call_lookup_model,
) -> RecordLookupDecision:
    payload = {
        "current_message": request.current_message.model_dump(mode="json"),
        "context_messages": [m.model_dump(mode="json") for m in request.context_messages],
        "reference_date": request.reference_date.isoformat(), "timezone": request.timezone,
        "conditions": conditions.model_dump(mode="json"),
    }
    prompt = (Path(__file__).parent / "prompts" / "decide_lookup.md").read_text(encoding="utf-8")
    decision = await invoke([SystemMessage(prompt), HumanMessage(json.dumps(payload, ensure_ascii=False))])
    if not isinstance(decision, RecordLookupDecision):
        raise AIInvalidResponseError("조회 판단이 정해진 타입이 아닙니다")
    evidence = decision.evidence
    if evidence.message_id != request.current_message.id or evidence.quote not in request.current_message.text:
        raise AIInvalidResponseError("조회 판단의 근거가 이번 발화에 없습니다")
    return decision
