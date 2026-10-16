"""인증 도메인 오케스트레이션.

이메일 발송은 실제 SMTP 없이 더미로 처리한다 — 토큰을 서버 로그에 남기고
테스트에서는 거기서 복사해 쓴다. 실제 발송은 별도 이슈.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Unauthorized, ValidationFailed
from app.core.security import hash_password, hash_token, new_token, verify_password
from app.models.auth import Account, Auth

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=30)
EMAIL_VERIFICATION_TTL = timedelta(hours=24)


async def signup(session: AsyncSession, *, email: str, password: str, name: str) -> Account:
    existing = await session.scalar(select(Account).where(Account.email == email))
    if existing is not None:
        raise ValidationFailed({"email": "이미 가입된 이메일입니다."})

    verification_token = new_token()
    account = Account(
        email=email,
        password_hash=hash_password(password),
        email_verified=False,
        email_verification_token_hash=hash_token(verification_token),
        email_verification_expires_at=datetime.now(UTC) + EMAIL_VERIFICATION_TTL,
    )
    session.add(account)
    await session.commit()
    # 더미 발송: 실제 메일 대신 콘솔에 남긴다 (name은 발송 문구용으로만 쓰고
    # 저장하지 않는다). logging이 아니라 print인 이유는 uvicorn --reload의
    # 리로더/워커 프로세스 분리 때문에 logging 설정이 매번 일관되게 먹지
    # 않아서다 — 이 더미 출력은 항상 눈에 보여야 한다.
    print(
        f"[더미 이메일 발송] {name}님({email}) 인증 토큰: {verification_token}",
        flush=True,
    )
    return account


async def verify_email(session: AsyncSession, *, token: str) -> Account:
    token_hash = hash_token(token)
    account = await session.scalar(
        select(Account).where(Account.email_verification_token_hash == token_hash)
    )
    if account is None:
        raise ValidationFailed({"token": "유효하지 않은 토큰입니다."})
    if (
        account.email_verification_expires_at is None
        or account.email_verification_expires_at < datetime.now(UTC)
    ):
        raise ValidationFailed({"token": "토큰이 만료되었습니다."})

    account.email_verified = True
    account.email_verification_token_hash = None
    account.email_verification_expires_at = None
    await session.commit()
    return account


async def _issue_session(session: AsyncSession, account: Account) -> tuple[str, str]:
    """세션(Auth) 행을 새로 만들고 (access, refresh) 원문 토큰을 돌려준다."""
    access_token = new_token()
    refresh_token = new_token()
    now = datetime.now(UTC)
    auth = Auth(
        account_id=account.id,
        access_token_hash=hash_token(access_token),
        access_token_expires_at=now + ACCESS_TOKEN_TTL,
        refresh_token_hash=hash_token(refresh_token),
        expires_at=now + REFRESH_TOKEN_TTL,
    )
    session.add(auth)
    await session.flush()
    return access_token, refresh_token


async def login(session: AsyncSession, *, email: str, password: str) -> tuple[str, str]:
    account = await session.scalar(select(Account).where(Account.email == email))
    if account is None or not account.password_hash:
        raise Unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")
    if not verify_password(password, account.password_hash):
        raise Unauthorized("이메일 또는 비밀번호가 올바르지 않습니다.")
    tokens = await _issue_session(session, account)
    await session.commit()
    return tokens


async def login_with_kakao(
    session: AsyncSession, *, kakao_user_id: str, email: str
) -> tuple[str, str]:
    """카카오 사용자 정보로 계정을 찾거나 만들고 세션을 발급한다 (업서트)."""
    account = await session.scalar(
        select(Account).where(Account.kakao_user_id == kakao_user_id)
    )
    if account is None:
        # 같은 이메일의 LOCAL 계정이 있으면 그 계정에 카카오를 연결한다.
        account = await session.scalar(select(Account).where(Account.email == email))
        if account is None:
            account = Account(
                email=email, kakao_user_id=kakao_user_id, email_verified=True
            )
            session.add(account)
        else:
            account.kakao_user_id = kakao_user_id
        await session.flush()
    tokens = await _issue_session(session, account)
    await session.commit()
    return tokens


async def refresh(session: AsyncSession, *, refresh_token: str) -> tuple[str, str]:
    token_hash = hash_token(refresh_token)
    auth = await session.scalar(select(Auth).where(Auth.refresh_token_hash == token_hash))
    if auth is None or auth.revoked_at is not None:
        raise Unauthorized("refresh token이 유효하지 않습니다.")
    if auth.expires_at < datetime.now(UTC):
        raise Unauthorized("refresh token이 만료되었습니다.")

    # 회전: 기존 세션은 끊고 새 세션을 발급한다.
    auth.revoked_at = datetime.now(UTC)
    account = await session.get(Account, auth.account_id)
    assert account is not None
    tokens = await _issue_session(session, account)
    await session.commit()
    return tokens


async def logout(session: AsyncSession, *, refresh_token: str) -> None:
    token_hash = hash_token(refresh_token)
    auth = await session.scalar(select(Auth).where(Auth.refresh_token_hash == token_hash))
    if auth is None:
        return
    auth.revoked_at = datetime.now(UTC)
    await session.commit()
