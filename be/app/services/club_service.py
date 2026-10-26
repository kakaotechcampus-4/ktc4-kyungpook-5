"""동아리·멤버십 도메인 오케스트레이션."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ClubCategory, InvitationStatus, MemberRole, MemberStatus
from app.core.exceptions import ValidationFailed
from app.core.security import hash_token, new_token
from app.models.auth import Account
from app.models.clubs import Club, Invitation, Member

INVITATION_TTL = timedelta(days=7)


async def create_club(
    session: AsyncSession,
    *,
    account: Account,
    name: str,
    category: ClubCategory | None,
    description: str | None,
    owner_name: str,
) -> tuple[Club, Member]:
    club = Club(name=name, category=category, description=description)
    session.add(club)
    await session.flush()

    owner = Member(
        club_id=club.id,
        account_id=account.id,
        name=owner_name,
        role=MemberRole.OWNER,
        status=MemberStatus.ACTIVE,
    )
    session.add(owner)
    await session.commit()
    return club, owner


async def list_my_clubs(session: AsyncSession, account: Account) -> list[Member]:
    """account가 속한 모든 동아리의 Member 행. Member.club이 lazy-load된다."""
    rows = await session.scalars(
        select(Member)
        .where(Member.account_id == account.id, Member.status == MemberStatus.ACTIVE)
        .join(Club, Member.club_id == Club.id)
    )
    members = list(rows)
    for member in members:
        await session.refresh(member, attribute_names=["club"])
    return members


async def create_invitation(
    session: AsyncSession,
    *,
    club_id: str,
    email: str,
    role: MemberRole,
    invited_by: Member,
) -> Invitation:
    token = new_token()
    invitation = Invitation(
        club_id=club_id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC) + INVITATION_TTL,
        invited_by=invited_by.id,
    )
    session.add(invitation)
    await session.commit()
    # 더미 발송: 실제 메일 대신 콘솔에 남긴다 (이유는 auth_service.signup 참고).
    print(f"[더미 초대 메일 발송] {email}에게 토큰: {token}", flush=True)
    return invitation


async def accept_invitation(
    session: AsyncSession, *, token: str, account: Account
) -> Member:
    token_hash = hash_token(token)
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == token_hash)
    )
    if invitation is None:
        raise ValidationFailed({"token": "유효하지 않은 초대입니다."})
    if invitation.status != InvitationStatus.PENDING:
        raise ValidationFailed({"token": "이미 처리된 초대입니다."})
    if invitation.expires_at < datetime.now(UTC):
        raise ValidationFailed({"token": "초대가 만료되었습니다."})

    existing = await session.scalar(
        select(Member).where(
            Member.club_id == invitation.club_id, Member.account_id == account.id
        )
    )
    if existing is not None:
        raise ValidationFailed({"token": "이미 동아리에 속해 있습니다."})

    member = Member(
        club_id=invitation.club_id,
        account_id=account.id,
        name=account.email.split("@")[0],
        role=invitation.role,
        status=MemberStatus.ACTIVE,
    )
    session.add(member)

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_by = account.id
    invitation.accepted_at = datetime.now(UTC)

    await session.commit()
    return member
