"""회의 발화에서 확인할 일정과 할 일만 제안한다."""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import AwareDatetime, Field, field_validator, model_validator

from ...contracts import ContractModel, NonBlankStr
from ...llm import ainvoke_structured
from .context import MEETING_CONTEXT_UTTERANCES
from .schemas import MeetingUtterance


class TaskExtractionRequest(ContractModel):
    meeting_id: str
    club_id: str
    utterance: MeetingUtterance
    context: tuple[MeetingUtterance, ...] = ()
    timezone: str
    occurred_at: AwareDatetime

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("유효한 IANA 시간대가 필요합니다") from error
        return value

    @model_validator(mode="after")
    def context_order(self) -> Self:
        seqs = [item.seq for item in self.context] + [self.utterance.seq]
        if any(a >= b for a, b in zip(seqs, seqs[1:])):
            raise ValueError("앞 발화는 순서대로 현재 발화보다 앞서야 합니다")
        return self


class TaskSuggestion(ContractModel):
    kind: Literal["TASK", "SCHEDULE"]
    title: NonBlankStr = Field(max_length=200)
    description: str | None = None
    suggested_assignee: str | None = Field(default=None, max_length=100)
    due_date: date | None = None
    due_at: AwareDatetime | None = None
    scheduled_at: AwareDatetime | None = None
    unresolved_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def mark_missing_confirmation_fields(self) -> Self:
        # 모델이 확인 필드를 빠뜨려도 BE에 미정 담당자와 정확한 시각을 알린다.
        fields = list(dict.fromkeys(self.unresolved_fields))
        time_field = "due_at" if self.kind == "TASK" else "scheduled_at"
        if getattr(self, time_field) is None and time_field not in fields:
            fields.append(time_field)
        if (self.suggested_assignee is None or not self.suggested_assignee.strip()) and "suggested_assignee" not in fields:
            fields.append("suggested_assignee")
        object.__setattr__(self, "unresolved_fields", fields)
        return self


class TaskExtractionResult(ContractModel):
    suggestions: list[TaskSuggestion]


@cache
def _prompt() -> str:
    return (Path(__file__).parent / "prompts" / "extract_tasks.md").read_text(encoding="utf-8")


def _messages(request: TaskExtractionRequest):
    # 발화는 지시가 아닌 데이터로 전달하고 문맥은 지시 대상 해석에만 쓴다.
    data = {
        "timezone": request.timezone,
        "occurred_at": request.occurred_at.astimezone(ZoneInfo(request.timezone)).isoformat(),
        "context": [item.text for item in request.context[-MEETING_CONTEXT_UTTERANCES:]],
        "utterance": request.utterance.text,
    }
    return [SystemMessage(_prompt()), HumanMessage(json.dumps(data, ensure_ascii=False))]


async def extract_task_suggestions(request: TaskExtractionRequest) -> TaskExtractionResult:
    """저장이나 예약 없이 후보만 반환하며 모델 오류는 그대로 전달한다."""
    return await ainvoke_structured(_messages(request), TaskExtractionResult)
