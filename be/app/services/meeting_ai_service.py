"""회의 AI 공개 경계 adapter. app.ai 외 내부 모듈/LLM을 우회 호출하지 않는다.

공개 계약이 없는 기능은 AI_PUBLIC_CONTRACT_UNAVAILABLE로 실패한다.
조회에는 소속 범위를 고정한 검색 port를 records 인자로 주입한다.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app import ai
from app.services.record_search_port import PostgresRecordSearch


class CandidateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["TASK", "SCHEDULE"] = "TASK"
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    suggested_assignee: str | None = Field(default=None, max_length=100)
    due_date: date | None = None
    due_at: AwareDatetime | None = None
    scheduled_at: AwareDatetime | None = None
    unresolved_fields: list[str] = Field(default_factory=list)


class PublicContractUnavailable(ai.AIConfigError):
    code = "AI_PUBLIC_CONTRACT_UNAVAILABLE"


def _public(name: str):
    value = getattr(ai, name, None)
    if value is None:
        raise PublicContractUnavailable(f"app.ai 공개 계약이 준비되지 않았습니다: {name}")
    return value


async def judge(payload: dict):
    request = _public("JudgeUtteranceRequest").model_validate(payload)
    result = await _public("judge_utterance")(
        request, records=PostgresRecordSearch(payload["club_id"])
    )
    if result.utterance_id != request.utterance.utterance_id or result.source_version != request.utterance.version:
        raise ai.AIInvalidResponseError("판단 결과의 발화 ID·버전이 요청과 다릅니다")
    return result


async def extract(payload: dict) -> list[CandidateDraft]:
    request_data = {
        **payload, "timezone": "Asia/Seoul",
        "occurred_at": payload["utterance"]["started_at"],
    }
    request = _public("TaskExtractionRequest").model_validate(request_data)
    result = await _public("extract_task_suggestions")(request)
    # 결과를 부분 저장하지 않는다. 잘못된 후보는 명시적인 기능 실패다.
    return [CandidateDraft.model_validate(item.model_dump()) for item in result.suggestions]
