"""인증 엔드포인트. LOCAL(이메일+비번)과 KAKAO 두 수단만 받는다."""

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_account
from app.core.exceptions import Unauthorized, ValidationFailed
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.auth import (
    EmailVerifyIn,
    EmailVerifyOut,
    KakaoLoginIn,
    LoginIn,
    LogoutIn,
    RefreshIn,
    SessionOut,
    SignupIn,
    SignupOut,
)
from app.schemas.common import Envelope
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"


@router.post("/signup", response_model=Envelope[SignupOut], status_code=201)
async def signup(
    body: SignupIn, session: AsyncSession = Depends(get_session)
) -> Envelope[SignupOut]:
    account = await auth_service.signup(
        session, email=body.email, password=body.password, name=body.name
    )
    return Envelope(data=SignupOut(id=account.id))


@router.post("/email/verify", response_model=Envelope[EmailVerifyOut])
async def verify_email(
    body: EmailVerifyIn, session: AsyncSession = Depends(get_session)
) -> Envelope[EmailVerifyOut]:
    account = await auth_service.verify_email(session, token=body.token)
    return Envelope(data=EmailVerifyOut(email_verified=account.email_verified))


@router.post("/login", response_model=Envelope[SessionOut])
async def login(
    body: LoginIn, session: AsyncSession = Depends(get_session)
) -> Envelope[SessionOut]:
    access_token, refresh_token = await auth_service.login(
        session, email=body.email, password=body.password
    )
    return Envelope(
        data=SessionOut(access_token=access_token, refresh_token=refresh_token)
    )


async def _exchange_kakao_code(code: str) -> tuple[str, str]:
    """인가 코드를 카카오 access token과 교환하고, 사용자 정보를 조회한다."""
    settings = get_settings()
    if not settings.kakao_rest_api_key or not settings.kakao_redirect_uri:
        raise ValidationFailed({"code": "카카오 로그인이 설정되지 않았습니다."})

    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    client_secret = settings.kakao_client_secret.get_secret_value()
    if client_secret:
        token_data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10) as client:
        token_res = await client.post(KAKAO_TOKEN_URL, data=token_data)
        if token_res.status_code != 200:
            raise Unauthorized("카카오 인가 코드 교환에 실패했습니다.")
        kakao_access_token = token_res.json()["access_token"]

        user_res = await client.get(
            KAKAO_USER_INFO_URL,
            headers={"Authorization": f"Bearer {kakao_access_token}"},
        )
        if user_res.status_code != 200:
            raise Unauthorized("카카오 사용자 정보 조회에 실패했습니다.")
        user = user_res.json()

    kakao_user_id = str(user["id"])
    email = user.get("kakao_account", {}).get("email")
    if not email:
        raise ValidationFailed({"email": "카카오 계정에 이메일 동의가 필요합니다."})
    return kakao_user_id, email


@router.post("/kakao/callback", response_model=Envelope[SessionOut])
async def kakao_callback(
    body: KakaoLoginIn, session: AsyncSession = Depends(get_session)
) -> Envelope[SessionOut]:
    if not body.code:
        raise ValidationFailed({"code": "code가 필요합니다."})
    kakao_user_id, email = await _exchange_kakao_code(body.code)
    access_token, refresh_token = await auth_service.login_with_kakao(
        session, kakao_user_id=kakao_user_id, email=email
    )
    return Envelope(
        data=SessionOut(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/refresh", response_model=Envelope[SessionOut])
async def refresh(
    body: RefreshIn, session: AsyncSession = Depends(get_session)
) -> Envelope[SessionOut]:
    access_token, refresh_token = await auth_service.refresh(
        session, refresh_token=body.refresh_token
    )
    return Envelope(
        data=SessionOut(access_token=access_token, refresh_token=refresh_token)
    )


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutIn,
    session: AsyncSession = Depends(get_session),
    _account: Account = Depends(get_current_account),
) -> None:
    await auth_service.logout(session, refresh_token=body.refresh_token)
