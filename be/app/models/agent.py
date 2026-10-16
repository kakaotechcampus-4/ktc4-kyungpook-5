"""BE ↔ AI 호출 로그, 비동기 작업, Jev 판단, mini 활동 이벤트.

호출 이력은 빠짐없이 남기고 수정·삭제하지 않는다 (NF4).
작업(agent_jobs)은 처리 상태, 판단(context_decisions)은 무엇을 하기로 했는지를
따로 남긴다 — 작업이 성공해도 판단이 NONE일 수 있다.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AgentFeature,
    AgentJobKind,
    AgentJobStage,
    AgentJobStatus,
    AgentRunStatus,
    ContextDecisionStatus,
    ContextSourceType,
    JudgeKind,
    JudgeRoute,
)
from app.db.base import Base, ID_LENGTH, IdMixin, JsonB, TimestampMixin, enum_column, fk


class AgentLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_log"
    __id_prefix__ = "alg"

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("events.id", ondelete="SET NULL")
    )
    feature: Mapped[AgentFeature] = mapped_column(
        enum_column(AgentFeature), nullable=False
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus), nullable=False
    )
    # 민감정보를 마스킹한 뒤 저장한다. 키·토큰은 남기지 않는다.
    request: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    response: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentJob(IdMixin, TimestampMixin, Base):
    """OCR·STT·판단·Discord 수집 작업 한 건.

    지금은 요청 안에서 바로 처리해 응답 시점에 이미 끝나 있다(실제 작업 큐 없음).
    그래도 상태 전이는 QUEUED → RUNNING → SUCCEEDED/FAILED 순서로 활동 이벤트에 남긴다.
    """

    __tablename__ = "agent_jobs"
    __id_prefix__ = "job"
    __table_args__ = (Index("ix_agent_jobs_club_status", "club_id", "status"),)

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    kind: Mapped[AgentJobKind] = mapped_column(enum_column(AgentJobKind), nullable=False)
    status: Mapped[AgentJobStatus] = mapped_column(
        enum_column(AgentJobStatus), nullable=False, default=AgentJobStatus.QUEUED
    )
    stage: Mapped[AgentJobStage | None] = mapped_column(enum_column(AgentJobStage))
    # 결과 리소스 연결. 예: {"receiptImportId": ...}, {"contextDecisionId": ...}
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 자동 작업(전사 확정·Discord 수집)이 만든 job은 요청자가 없다.
    created_by: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("members.id", ondelete="SET NULL")
    )


class ActivityEvent(Base):
    """mini 활동 스트림. id가 SSE 재접속 cursor다.

    문자열 PK는 사전순이 시간순이 아니라서 cursor로 쓸 수 없어 bigint 순번을 둔다.
    원문·비밀값은 payload에 넣지 않는다.
    """

    __tablename__ = "agent_activity_events"
    __table_args__ = (Index("ix_activity_events_club_id_id", "club_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    job_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("agent_jobs.id", ondelete="SET NULL")
    )
    kind: Mapped[AgentJobKind] = mapped_column(enum_column(AgentJobKind), nullable=False)
    status: Mapped[AgentJobStatus] = mapped_column(
        enum_column(AgentJobStatus), nullable=False
    )
    stage: Mapped[AgentJobStage | None] = mapped_column(enum_column(AgentJobStage))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContextDecision(IdMixin, TimestampMixin, Base):
    """회의 발화·Discord 대화에 대한 Jev 판단(RAG/LLM/NONE)과 그 결과.

    근거는 원문 id와 판단 당시 version으로 sources에 고정한다. 원문이 바뀌면
    status를 STALE로 바꾸고 새 판단을 만든다(덮어쓰지 않는다).
    """

    __tablename__ = "context_decisions"
    __id_prefix__ = "cdc"
    __table_args__ = (
        Index("ix_context_decisions_club_source", "club_id", "source_type"),
    )

    club_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("clubs.id"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String(ID_LENGTH), fk("agent_jobs.id"), nullable=False
    )
    source_type: Mapped[ContextSourceType] = mapped_column(
        enum_column(ContextSourceType), nullable=False
    )
    # 목록 필터용. 원문 종류에 따라 둘 중 하나만 채운다.
    meeting_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("meetings.id"), index=True
    )
    discord_connection_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH), fk("discord_connections.id"), index=True
    )
    # [{"sourceId": ..., "sourceVersion": ...}] — 판단에 쓴 원문과 그 버전
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JsonB, nullable=False)
    status: Mapped[ContextDecisionStatus] = mapped_column(
        enum_column(ContextDecisionStatus), nullable=False
    )
    route: Mapped[JudgeRoute] = mapped_column(enum_column(JudgeRoute), nullable=False)
    kind: Mapped[JudgeKind] = mapped_column(enum_column(JudgeKind), nullable=False)
    # 화면에 보여줄 짧은 판단 이유. 모델 내부 추론 전문이 아니다.
    reason_summary: Mapped[str | None] = mapped_column(Text)
    # RAG 검색어
    question: Mapped[str | None] = mapped_column(Text)
    # RAG 답변 또는 LLM 생성 결과. NONE이면 null.
    output: Mapped[str | None] = mapped_column(Text)
    # RecordSource 모양 [{"recordId", "fileName", "location": {"label"}}]
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # [{"tool", "status", "durationMs", ...}] NONE이면 빈 배열.
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JsonB, nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
