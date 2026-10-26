"""작업·Jev 판단·mini 활동 요청·응답 스키마."""

from typing import Any

from app.core.enums import (
    AgentJobKind,
    AgentJobStage,
    AgentJobStatus,
    CharacterState,
    ContextDecisionStatus,
    ContextSourceType,
    DiscordConnectionStatus,
    JudgeKind,
    JudgeRoute,
)
from app.schemas.common import CamelModel, UtcDateTime


class AgentJobOut(CamelModel):
    id: str
    kind: AgentJobKind
    status: AgentJobStatus
    stage: AgentJobStage | None
    # 결과 리소스 id. 예: contextDecisionId, receiptImportId
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: UtcDateTime | None
    finished_at: UtcDateTime | None
    created_at: UtcDateTime


class ContextDecisionOut(CamelModel):
    id: str
    job_id: str
    source_type: ContextSourceType
    meeting_id: str | None
    connection_id: str | None
    sources: list[dict[str, Any]]
    status: ContextDecisionStatus
    route: JudgeRoute
    kind: JudgeKind
    reason_summary: str | None
    question: str | None
    output: str | None
    citations: list[dict[str, Any]] | None
    tool_calls: list[dict[str, Any]]
    model_version: str
    policy_version: str
    created_at: UtcDateTime


class ActivityJobOut(CamelModel):
    id: str
    kind: AgentJobKind
    status: AgentJobStatus
    stage: AgentJobStage | None
    modified_at: UtcDateTime


class ActivityConnectionOut(CamelModel):
    id: str
    status: DiscordConnectionStatus
    enabled: bool


class ActivitySnapshotOut(CamelModel):
    # SSE Last-Event-ID로 넘길 마지막 이벤트 id. 이벤트가 없으면 "0".
    cursor: str
    character_state: CharacterState
    # 진행 중인 작업과 최근 실패한 작업
    jobs: list[ActivityJobOut]
    connections: list[ActivityConnectionOut]
    # 아직 검토하지 않은 할 일 후보 수. ATTENTION 판단에 쓴다.
    proposed_task_count: int
