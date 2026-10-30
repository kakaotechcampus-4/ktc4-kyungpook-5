"""동아리·멤버십 도메인 오케스트레이션."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ClubCategory, InvitationStatus, MemberRole, MemberStatus, SERVICE_ROLES
from app.core.exceptions import ValidationFailed
from app.core.security import hash_token, new_token
from app.models.auth import Account, Auth
from app.models.clubs import Club, Invitation, Member

INVITATION_TTL = timedelta(days=7)

# 임원 직책(회장·홍보부장 등)은 ERD에서 축소하기로 해 role만으로 subtitle을 정한다.
_OFFICER_SUBTITLE = {MemberRole.OWNER: "대표", MemberRole.MANAGER: "운영진"}

_CLUB_CATEGORY_LABEL = {
    ClubCategory.ACADEMIC: "학술",
    ClubCategory.SPORTS: "운동",
    ClubCategory.VOLUNTEER: "봉사",
    ClubCategory.HOBBY: "취미",
    ClubCategory.ETC: "기타",
}

# 검색 결과가 과하게 많아지는 것만 막는다 — 페이지네이션은 두지 않는다(#189).
CLUB_SEARCH_LIMIT = 20


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
    """회장·임원으로 이용할 수 있는 소속만 돌려준다. 일반 명단은 노출하지 않는다."""
    rows = await session.scalars(
        select(Member)
        .where(Member.account_id == account.id, Member.status == MemberStatus.ACTIVE,
               Member.role.in_(SERVICE_ROLES))
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
    email: str | None = None,
    role: MemberRole,
    invited_by: Member,
) -> Invitation:
    if role not in SERVICE_ROLES:
        raise ValidationFailed({"role": "회장·임원 역할만 초대할 수 있습니다."})
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
    # 원문은 DB에 저장하지 않고 생성 응답에서 한 번만 보여 준다.
    # 실제 메일 발송은 지원하지 않으므로 콘솔에는 비밀 토큰을 남기지 않는다.
    invitation._one_time_token = token  # type: ignore[attr-defined]
    return invitation


async def accept_invitation(
    session: AsyncSession, *, token: str, account: Account
) -> Member:
    token_hash = hash_token(token)
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == token_hash).with_for_update()
    )
    if invitation is None:
        raise ValidationFailed({"token": "유효하지 않은 초대입니다."})
    if invitation.status != InvitationStatus.PENDING:
        raise ValidationFailed({"token": "이미 처리된 초대입니다."})
    if invitation.expires_at < datetime.now(UTC):
        raise ValidationFailed({"token": "초대가 만료되었습니다."})
    if invitation.role not in SERVICE_ROLES:
        raise ValidationFailed({"role": "일반 동아리원 초대는 서비스에서 사용할 수 없습니다. 회장·임원 초대를 요청해 주세요."})

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


def _group_and_subtitle(role: MemberRole, student_no: str | None) -> tuple[str, str]:
    if role in _OFFICER_SUBTITLE:
        return "임원", _OFFICER_SUBTITLE[role]
    return "동아리원", f"{student_no}학번" if student_no else "동아리원"


async def list_members(session: AsyncSession, *, club_id: str) -> list[dict]:
    """명단 + 수락 대기 초대. 초대는 아직 Member 행이 없어 따로 합친다.

    페이지네이션 없이 전체를 내린다(#188) — 동아리 규모상 과한 설계로 보임.
    """
    members = await session.scalars(
        select(Member)
        .where(Member.club_id == club_id, Member.status == MemberStatus.ACTIVE)
        .order_by(Member.name)
    )
    rows: list[dict] = []
    for member in members:
        group, subtitle = _group_and_subtitle(member.role, member.student_no)
        account_status = "NONE"
        account_at = None
        if member.account_id:
            account_status = "JOINED"
            account_at = await session.scalar(
                select(func.max(Auth.created_at)).where(
                    Auth.account_id == member.account_id
                )
            )
        account = await session.get(Account, member.account_id) if member.account_id else None
        rows.append(
            {
                "id": member.id,
                "name": member.name,
                "group": group,
                "subtitle": subtitle,
                "contact": member.phone or (account.email if account else None),
                "account": account_status,
                "account_at": account_at,
            }
        )

    invitations = await session.scalars(
        select(Invitation).where(
            Invitation.club_id == club_id,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at >= datetime.now(UTC),
        )
    )
    for invitation in invitations:
        group, subtitle = _group_and_subtitle(invitation.role, None)
        rows.append(
            {
                "id": invitation.id,
                # 링크 초대는 수신자 이메일을 보관하지 않는다.
                "name": "초대 링크 대기",
                "group": group,
                "subtitle": subtitle,
                "contact": None,
                "account": "INVITED",
                "account_at": invitation.created_at,
            }
        )
    return rows


async def search_clubs(session: AsyncSession, *, query: str) -> list[dict]:
    """동아리 이름 일부로 찾는다. 로그인 전에도 부를 수 있어 동아리원 확인을 안 한다."""
    clubs = await session.scalars(
        select(Club)
        .where(Club.name.ilike(f"%{query}%"))
        .order_by(Club.name)
        .limit(CLUB_SEARCH_LIMIT)
    )
    rows: list[dict] = []
    for club in clubs:
        owner = await session.scalar(
            select(Member).where(
                Member.club_id == club.id,
                Member.role == MemberRole.OWNER,
                Member.status == MemberStatus.ACTIVE,
            )
        )
        executive_count = await session.scalar(
            select(func.count())
            .select_from(Member)
            .where(
                Member.club_id == club.id,
                Member.role.in_((MemberRole.OWNER, MemberRole.MANAGER)),
                Member.status == MemberStatus.ACTIVE,
            )
        )
        rows.append(
            {
                "id": club.id,
                "name": club.name,
                "field": _CLUB_CATEGORY_LABEL.get(club.category, "기타"),
                "owner_name": owner.name if owner else "",
                "executive_count": executive_count or 0,
            }
        )
    return rows
