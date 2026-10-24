"""대화 Agent 한 턴의 내부 계약과 그래프 상태. 공개 BE 계약은 아니다."""

from typing import Annotated, Self, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph.message import add_messages
from pydantic import Field, field_validator, model_validator

from ....contracts import ContractModel, NonBlankStr
from ..schemas import CalendarDate, PlanningMessage
from .state import PlanningDraft
from .record_tool import RecordLookupResult
from .tools import ConditionUpdateResult
from ..generation.schemas import PlanGenerationResult, PlanningGenerationState
from ..generation.offers import OfferUpdateResult


def validate_planning_history(history: tuple[AnyMessage, ...], current_message_id: str | None = None) -> None:
    """버튼은 이번 발화가 없어도 같은 이력 검증을 사용한다. 가짜 사용자 메시지는 만들지 않는다."""
    pending: set[str] = set()
    seen: set[str] = set()
    for message in history:
        if not isinstance(message, (HumanMessage, AIMessage, ToolMessage)):
            raise ValueError("대화 이력에는 사용자·AI·Tool 메시지만 허용합니다")
        if isinstance(message, ToolMessage):
            if message.tool_call_id not in pending:
                raise ValueError("Tool 결과에 대응하는 호출이 없습니다")
            pending.remove(message.tool_call_id)
            continue
        if pending:
            raise ValueError("Tool 호출 뒤에 실행 결과가 필요합니다")
        if isinstance(message, HumanMessage) and current_message_id is not None and message.id == current_message_id:
            raise ValueError("이번 사용자 메시지가 이미 이력에 있습니다")
        if isinstance(message, AIMessage):
            if message.invalid_tool_calls:
                raise ValueError("잘못된 Tool 호출 이력입니다")
            ids = [call["id"] for call in message.tool_calls]
            if any(not item or item in seen for item in ids) or len(ids) != len(set(ids)):
                raise ValueError("Tool 호출 ID는 비어 있거나 중복될 수 없습니다")
            pending.update(ids)
            seen.update(ids)
    if pending:
        raise ValueError("실행 결과가 없는 Tool 호출 이력입니다")


class PlanningAgentTurnInput(ContractModel):
    draft: PlanningDraft
    current_message: PlanningMessage
    history: tuple[AnyMessage, ...] = Field(default=(), max_length=60)
    reference_date: CalendarDate
    timezone: NonBlankStr = "Asia/Seoul"
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("유효한 IANA 시간대가 필요합니다") from error
        return value

    @model_validator(mode="after")
    def _valid_dialog(self) -> Self:
        if self.current_message.role != "user":
            raise ValueError("이번 발화는 사용자 메시지여야 합니다")
        validate_planning_history(self.history, self.current_message.id)
        return self


class ToolExecution(ContractModel):
    tool_call_id: NonBlankStr
    name: NonBlankStr
    result: ConditionUpdateResult | RecordLookupResult | OfferUpdateResult | PlanGenerationResult


class PlanningAgentState(TypedDict):
    # Node는 이번에 추가할 메시지만 반환한다. add_messages가 앞선 대화에 이어 붙인다.
    messages: Annotated[list[AnyMessage], add_messages]
    draft: PlanningDraft
    executions: list[ToolExecution]
    tool_calls: int
    model_calls: int
    limit_reached: bool
    record_lookup: RecordLookupResult | None
    generation: PlanningGenerationState
    generation_result: PlanGenerationResult | None
    generation_model_calls: int


class PlanningAgentTurnResult(ContractModel):
    reply: NonBlankStr
    draft: PlanningDraft
    history: tuple[AnyMessage, ...]
    executions: tuple[ToolExecution, ...]
    model_calls: int
    limit_reached: bool
    prompt_version: NonBlankStr
    record_lookup: RecordLookupResult | None = None
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)
    generation_result: PlanGenerationResult | None = None
    generation_model_calls: int = 0
    preview_is_current: bool = False
