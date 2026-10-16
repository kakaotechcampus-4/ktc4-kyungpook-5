"""Idempotency-Key 처리.

이번 작업(#131)의 auth·clubs 엔드포인트는 Idempotency-Key를 쓰지 않는다
(curl 계약에 헤더가 없다). 이후 회계·회의 등 실제 금전/비동기 작업을 만드는
라우터가 이 헬퍼를 가져다 쓴다.
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyConflict
from app.models.common import IdempotencyKey


@dataclass
class IdempotencyResult:
    record: IdempotencyKey
    is_replay: bool  # True면 저장된 response_status/response_body를 그대로 돌려준다


async def resolve(
    session: AsyncSession,
    *,
    key: str | None,
    club_id: str | None,
    member_id: str,
    endpoint: str,
    request_body: bytes,
) -> IdempotencyResult | None:
    """key가 없으면 None. 있으면 기존 레코드를 재사용하거나 새로 만든다."""
    if not key:
        return None

    body_hash = hashlib.sha256(request_body).hexdigest()
    existing = await session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.member_id == member_id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.request_body_hash != body_hash:
            raise IdempotencyConflict()
        is_done = existing.status == "COMPLETED"
        return IdempotencyResult(record=existing, is_replay=is_done)

    record = IdempotencyKey(
        club_id=club_id,
        member_id=member_id,
        endpoint=endpoint,
        idempotency_key=key,
        request_body_hash=body_hash,
        status="PROCESSING",
    )
    session.add(record)
    await session.flush()
    return IdempotencyResult(record=record, is_replay=False)


async def save_response(
    session: AsyncSession, record: IdempotencyKey, *, status_code: int, body: dict
) -> None:
    record.status = "COMPLETED"
    record.response_status = status_code
    record.response_body = body
    await session.flush()
