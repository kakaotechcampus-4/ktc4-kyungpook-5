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


async def resolve_account_by_token(
    token: str, session: AsyncSession
) -> Account | None:
    """access token 원문으로 Account를 찾는다. 유효하지 않으면 None.

    브라우저 WebSocket은 커스텀 헤더를 못 보내 쿼리 파라미터로 토큰을 받는
    경로(routers/meetings.py)가 따로 있어, 예외를 던지는 get_current_account와
    분리해둔다.
    """
    if not token:
        return None
    token_hash = hash_token(token)
    auth = await session.scalar(
        select(Auth).where(Auth.access_token_hash == token_hash)
    )
    if auth is None or auth.revoked_at is not None:
        return None
    if auth.access_token_expires_at < datetime.now(UTC):
        return None
    return await session.get(Account, auth.account_id)


async def get_current_account(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> Account:
    if not authorization or not authorization.startswith("Bearer "):
        raise Unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise Unauthorized()

    account = await resolve_account_by_token(token, session)
    if account is None:
        raise Unauthorized()
    return account


async def ensure_member(
    session: AsyncSession,
    *,
    club_id: str,
    account: Account,
    allowed: tuple[MemberRole, ...] | None = None,
) -> Member:
    """현재 계정이 club_id 동아리의 활성 동아리원인지 확인한다. 아니면 403.

    경로에 club_id가 없는 라우트(/meetings/{id}, /agent-jobs/{id} 등)는 리소스를
    먼저 조회해 club_id를 얻은 뒤 이 함수를 직접 부른다.
    """
    member = await session.scalar(
        select(Member).where(
            Member.club_id == club_id, Member.account_id == account.id
        )
    )
    if member is None or member.status != MemberStatus.ACTIVE:
        raise Forbidden("이 동아리에 속한 운영진만 할 수 있습니다.")
    if allowed is not None and member.role not in allowed:
        raise Forbidden("이 역할만 할 수 있습니다.")
    return member


async def require_member(
    club_id: str,
    account: Annotated[Account, Depends(get_current_account)],
    session: AsyncSession = Depends(get_session),
) -> Member:
    """경로의 club_id에 현재 계정이 속해 있는지 확인한다. 아니면 403."""
    return await ensure_member(session, club_id=club_id, account=account)


def require_club_role(*allowed: MemberRole):
    """역할이 allowed에 없으면 403. 예: require_club_role(MemberRole.OWNER)."""

    async def dependency(
        member: Annotated[Member, Depends(require_member)],
    ) -> Member:
        if member.role not in allowed:
            raise Forbidden("이 역할만 할 수 있습니다.")
        return member

    return dependency


# 자료 확정·연결 변경·할 일 수락처럼 결과를 바꾸는 요청에 쓴다.
WRITER_ROLES = (MemberRole.OWNER, MemberRole.MANAGER)
