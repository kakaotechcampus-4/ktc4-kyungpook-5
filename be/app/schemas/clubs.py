"""동아리·멤버십 도메인 요청·응답 스키마."""

from typing import Literal

from pydantic import EmailStr

from app.core.enums import ClubCategory
from app.schemas.common import CamelModel, ServiceMemberRole, UtcDateTime


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
    role: ServiceMemberRole


class MeOut(CamelModel):
    id: str
    email: str
    email_verified: bool
    clubs: list[MyClubOut]


class InvitationCreateIn(CamelModel):
    email: EmailStr
    role: ServiceMemberRole


class InvitationCreateOut(CamelModel):
    id: str


class InvitationAcceptIn(CamelModel):
    token: str


class InvitationAcceptOut(CamelModel):
    club_id: str
    role: ServiceMemberRole


# --- 동아리원 목록 (#188) --------------------------------------------------


class MemberOut(CamelModel):
    id: str
    name: str
    # 임원 직책(회장·홍보부장 등)은 ERD에서 축소하기로 해 role 2단계만 쓴다.
    group: Literal["임원", "동아리원"]
    subtitle: str
    contact: str | None
    account: Literal["JOINED", "INVITED", "NONE"]
    # 계정 있음이면 최근 로그인 시각, 초대함이면 초대 보낸 시각. 문구는 FE가 꾸민다.
    account_at: UtcDateTime | None


class MemberListResponse(CamelModel):
    data: list[MemberOut]
    meta: None = None


# --- 동아리 검색 (#189) -----------------------------------------------------


class ClubSearchOut(CamelModel):
    id: str
    name: str
    field: str
    owner_name: str
    executive_count: int


class ClubSearchListResponse(CamelModel):
    data: list[ClubSearchOut]
    meta: None = None
