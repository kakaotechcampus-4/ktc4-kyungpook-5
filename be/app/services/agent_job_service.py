"""비동기 작업(agent_jobs) 상태 전이와 mini 활동 이벤트 기록.

상태가 바뀔 때마다 활동 이벤트를 같은 트랜잭션에 추가한다 — 커밋되지 않은 상태가
SSE로 먼저 나가지 않게 하기 위해서다. 커밋은 호출하는 서비스가 한다.

지금은 실제 작업 큐가 없어 요청 안에서 바로 처리한다. 그래도 QUEUED → RUNNING →
SUCCEEDED/FAILED를 모두 남겨 나중에 큐로 옮겨도 이벤트 모양이 같게 한다.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AgentJobKind, AgentJobStage, AgentJobStatus
from app.core.exceptions import ApiError
from app.models.agent import ActivityEvent, AgentJob


class AgentJobNotFound(ApiError):
    status_code = 404
    code = "AGENT_JOB_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 작업을 찾을 수 없습니다.")


def _record(session: AsyncSession, job: AgentJob) -> None:
    session.add(
        ActivityEvent(
            club_id=job.club_id,
            job_id=job.id,
            kind=job.kind,
            status=job.status,
            stage=job.stage,
        )
    )


async def create_job(
    session: AsyncSession,
    *,
    club_id: str,
    kind: AgentJobKind,
    created_by: str | None = None,
) -> AgentJob:
    job = AgentJob(
        club_id=club_id, kind=kind, status=AgentJobStatus.QUEUED, created_by=created_by
    )
    session.add(job)
    # 이벤트가 job.id를 참조하므로 먼저 id를 받는다.
    await session.flush()
    _record(session, job)
    return job


def start(session: AsyncSession, job: AgentJob, stage: AgentJobStage | None) -> None:
    job.status = AgentJobStatus.RUNNING
    job.stage = stage
    job.started_at = datetime.now(UTC)
    _record(session, job)


def set_stage(session: AsyncSession, job: AgentJob, stage: AgentJobStage) -> None:
    job.stage = stage
    _record(session, job)


def succeed(session: AsyncSession, job: AgentJob, result: dict[str, Any]) -> None:
    job.status = AgentJobStatus.SUCCEEDED
    job.result = result
    job.finished_at = datetime.now(UTC)
    _record(session, job)


def fail(session: AsyncSession, job: AgentJob, error: dict[str, Any]) -> None:
    job.status = AgentJobStatus.FAILED
    job.error = error
    job.finished_at = datetime.now(UTC)
    _record(session, job)


async def get_job(session: AsyncSession, *, job_id: str) -> AgentJob:
    job = await session.get(AgentJob, job_id)
    if job is None:
        raise AgentJobNotFound()
    return job
