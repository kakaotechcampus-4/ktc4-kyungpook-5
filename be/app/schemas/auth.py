"""인증 도메인 요청·응답 스키마."""

from pydantic import EmailStr

from app.schemas.common import CamelModel


class SignupIn(CamelModel):
    email: EmailStr
    password: str
    name: str


class SignupOut(CamelModel):
    id: str


class EmailVerifyIn(CamelModel):
    token: str


class EmailVerifyOut(CamelModel):
    email_verified: bool


class LoginIn(CamelModel):
    email: EmailStr
    password: str


class SessionOut(CamelModel):
    access_token: str
    refresh_token: str


class RefreshIn(CamelModel):
    refresh_token: str


class LogoutIn(CamelModel):
    refresh_token: str


class KakaoLoginIn(CamelModel):
    """실제 카카오 콜백(code 교환)과, TEST_MODE 전용 우회가 함께 쓰는 입력.

    code가 있으면 카카오 토큰 엔드포인트와 교환해 kakaoUserId·email을 받아온다.
    TEST_MODE 전용 경로에서는 code 없이 kakaoUserId·email을 직접 받는다.
    """

    code: str | None = None
    kakao_user_id: str | None = None
    email: EmailStr | None = None
