"""동아리·멤버십 도메인 요청·응답 스키마."""

from pydantic import EmailStr

from app.core.enums import ClubCategory, MemberRole
from app.schemas.common import CamelModel


class ClubCreateIn(CamelModel):
    name: str
    category: ClubCategory | None = None
    description: str | None = None


class ClubOut(CamelModel):
    id: str
    name: str
    category: ClubCategory | None
    description: str | None


class MyClubOut(CamelModel):
    """내 소속 동아리 하나. club 정보 + 내 역할."""

    id: str
    name: str
    role: MemberRole


class MeOut(CamelModel):
    id: str
    email: str
    email_verified: bool
    clubs: list[MyClubOut]


class InvitationCreateIn(CamelModel):
    email: EmailStr
    role: MemberRole


class InvitationCreateOut(CamelModel):
    id: str


class InvitationAcceptIn(CamelModel):
    token: str


class InvitationAcceptOut(CamelModel):
    club_id: str
    role: MemberRole
