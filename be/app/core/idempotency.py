"""Idempotency-Key 처리.

이번 작업(#131)의 auth·clubs 엔드포인트는 Idempotency-Key를 쓰지 않는다
(curl 계약에 헤더가 없다). 이후 회계·회의 등 실제 금전/비동기 작업을 만드는
라우터가 이 헬퍼를 가져다 쓴다.

같은 키는 다음처럼 처리한다.
- 처음 온 요청: PROCESSING 레코드를 만들고 처리한다.
- 처리가 끝난 키: 저장한 응답을 그대로 돌려준다(재생).
- 아직 처리 중인 키: 다시 실행하지 않고 IdempotencyInProgress(409)를 낸다.
- 처리에 실패한 키: 호출 쪽이 release()로 지워 같은 키로 다시 시도할 수 있게 한다.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IdempotencyConflict, IdempotencyInProgress
from app.models.common import IdempotencyKey

# 서버가 처리 도중 죽어 PROCESSING으로 남은 키를 새 요청이 이어받기까지의 시간.
# AI 호출 한 번의 대기 상한(기본 60초)보다 충분히 길게 둔다.
STALE_PROCESSING_AFTER = timedelta(minutes=5)


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
        if existing.status == "COMPLETED":
            return IdempotencyResult(record=existing, is_replay=True)
        if datetime.now(UTC) - existing.modified_at < STALE_PROCESSING_AFTER:
            raise IdempotencyInProgress()
        # 오래된 PROCESSING은 처리하던 서버가 사라진 것으로 보고 이어받는다. 같은 키의
        # 재요청 둘이 동시에 이 행을 읽을 수 있어, 읽은 시각 그대로일 때만 갱신하는
        # 조건부 UPDATE로 한 요청만 이어받게 한다. 늦은 쪽은 앞 요청이 커밋할 때까지
        # 행 잠금에서 기다린 뒤 조건이 맞지 않아 0건이 된다(PR #209 리뷰).
        taken = await session.execute(
            update(IdempotencyKey)
            .where(
                IdempotencyKey.id == existing.id,
                IdempotencyKey.status == "PROCESSING",
                IdempotencyKey.modified_at == existing.modified_at,
            )
            .values(modified_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        if taken.rowcount != 1:
            raise IdempotencyInProgress()
        await session.refresh(existing)
        return IdempotencyResult(record=existing, is_replay=False)

    record = IdempotencyKey(
        club_id=club_id,
        member_id=member_id,
        endpoint=endpoint,
        idempotency_key=key,
        request_body_hash=body_hash,
        status="PROCESSING",
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError:
        # 같은 키의 첫 요청 두 개가 동시에 들어와 다른 쪽이 먼저 만들었다.
        await session.rollback()
        raise IdempotencyInProgress() from None
    return IdempotencyResult(record=record, is_replay=False)


async def save_response(
    session: AsyncSession, record: IdempotencyKey, *, status_code: int, body: dict
) -> None:
    record.status = "COMPLETED"
    record.response_status = status_code
    record.response_body = body
    await session.flush()


async def release(session: AsyncSession, record_id: str) -> None:
    """처리에 실패한 키를 지운다. 같은 키로 다시 보내면 처음부터 처리한다."""
    await session.execute(delete(IdempotencyKey).where(IdempotencyKey.id == record_id))
    await session.flush()
