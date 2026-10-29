"""동아리·멤버십 엔드포인트."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_account, require_club_role, require_member
from app.core.enums import MemberRole
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.schemas.clubs import (
    ClubCreateIn,
    ClubOut,
    ClubSearchListResponse,
    ClubSearchOut,
    InvitationAcceptIn,
    InvitationAcceptOut,
    InvitationCreateIn,
    InvitationCreateOut,
    MeOut,
    MemberListResponse,
    MemberOut,
    MyClubOut,
)
from app.schemas.common import Envelope
from app.services import club_service

router = APIRouter(prefix="/api/v1", tags=["clubs"])


@router.get("/me", response_model=Envelope[MeOut])
async def get_me(
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[MeOut]:
    members = await club_service.list_my_clubs(session, account)
    clubs = [
        MyClubOut(id=member.club.id, name=member.club.name, role=member.role)
        for member in members
    ]
    return Envelope(
        data=MeOut(
            id=account.id,
            email=account.email,
            email_verified=account.email_verified,
            clubs=clubs,
        )
    )


@router.get("/clubs", response_model=ClubSearchListResponse)
async def search_clubs(
    query: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> ClubSearchListResponse:
    """이름 일부로 동아리를 찾는다. 회원가입 중(로그인 전)에도 호출된다."""
    rows = await club_service.search_clubs(session, query=query)
    return ClubSearchListResponse(data=[ClubSearchOut.model_validate(row) for row in rows])


@router.post("/clubs", response_model=Envelope[ClubOut], status_code=201)
async def create_club(
    body: ClubCreateIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[ClubOut]:
    # 회원가입 시 받은 이름이 따로 없어, 생성자 표시 이름은 이메일 로컬파트로 둔다.
    # 마이페이지에서 고칠 수 있다(#106 범위 밖, 추후 연결).
    owner_name = account.email.split("@")[0]
    club, _owner = await club_service.create_club(
        session,
        account=account,
        name=body.name,
        category=body.category,
        description=body.description,
        owner_name=owner_name,
    )
    return Envelope(
        data=ClubOut(
            id=club.id,
            name=club.name,
            category=club.category,
            description=club.description,
        )
    )


@router.post(
    "/clubs/{club_id}/invitations",
    response_model=Envelope[InvitationCreateOut],
    status_code=201,
)
async def create_invitation(
    club_id: str,
    body: InvitationCreateIn,
    inviter: Member = Depends(require_club_role(MemberRole.OWNER, MemberRole.MANAGER)),
    session: AsyncSession = Depends(get_session),
) -> Envelope[InvitationCreateOut]:
    invitation = await club_service.create_invitation(
        session,
        club_id=club_id,
        email=body.email,
        role=body.role,
        invited_by=inviter,
    )
    return Envelope(data=InvitationCreateOut(id=invitation.id))


@router.post("/invitations/accept", response_model=Envelope[InvitationAcceptOut])
async def accept_invitation(
    body: InvitationAcceptIn,
    account: Account = Depends(get_current_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[InvitationAcceptOut]:
    member = await club_service.accept_invitation(
        session, token=body.token, account=account
    )
    return Envelope(
        data=InvitationAcceptOut(club_id=member.club_id, role=member.role)
    )


@router.get("/clubs/{club_id}/members", response_model=MemberListResponse)
async def list_members(
    club_id: str,
    _member: Member = Depends(require_member),
    session: AsyncSession = Depends(get_session),
) -> MemberListResponse:
    rows = await club_service.list_members(session, club_id=club_id)
    return MemberListResponse(data=[MemberOut.model_validate(row) for row in rows])
