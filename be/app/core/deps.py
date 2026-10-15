"""라우터 의존성.

DB 세션 하나가 요청 하나를 책임진다. 인증은 JWT가 아니라 DB 세션이라, 매
요청마다 access token을 `auth` 테이블로 검증한다 — 로그아웃·계정 정지 시
즉시 끊어야 해서다(#131).
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MemberRole, MemberStatus
from app.core.exceptions import Forbidden, Unauthorized
from app.core.security import hash_token
from app.db.session import get_session
from app.models.auth import Account, Auth
from app.models.clubs import Member


async def get_current_account(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Account:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise Unauthorized()

    token_hash = hash_token(token)
    auth = await session.scalar(
        select(Auth).where(Auth.access_token_hash == token_hash)
    )
    if auth is None or auth.revoked_at is not None:
        raise Unauthorized()
    if auth.access_token_expires_at < datetime.now(UTC):
        raise Unauthorized("access token이 만료되었습니다.")

    account = await session.get(Account, auth.account_id)
    if account is None:
        raise Unauthorized()
    return account


async def require_member(
    club_id: str,
    account: Annotated[Account, Depends(get_current_account)],
    session: AsyncSession = Depends(get_session),
) -> Member:
    """경로의 club_id에 현재 계정이 속해 있는지 확인한다. 아니면 403."""
    member = await session.scalar(
        select(Member).where(
            Member.club_id == club_id, Member.account_id == account.id
        )
    )
    if member is None or member.status != MemberStatus.ACTIVE:
        raise Forbidden("이 동아리에 속한 운영진만 할 수 있습니다.")
    return member


def require_club_role(*allowed: MemberRole):
    """역할이 allowed에 없으면 403. 예: require_club_role(MemberRole.OWNER)."""

    async def dependency(
        member: Annotated[Member, Depends(require_member)],
    ) -> Member:
        if member.role not in allowed:
            raise Forbidden("이 역할만 할 수 있습니다.")
        return member

    return dependency
