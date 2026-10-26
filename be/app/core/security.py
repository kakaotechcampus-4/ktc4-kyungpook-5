"""비밀번호 해시와 토큰 생성·해시.

비밀번호는 저엔트로피(사람이 고른 값)라 PBKDF2(솔트+반복)로 늘려 저장한다.
access/refresh/이메일인증/초대 토큰은 고엔트로피 난수라 원문을 그대로 서버가
한 번만 보여주고, DB에는 SHA-256 해시만 남긴다 — 되돌릴 필요가 없어서 단순한
해시로 충분하다.
"""

import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt, _, expected_hex = password_hash.partition("$")
    if not salt or not expected_hex:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest.hex(), expected_hex)


def new_token() -> str:
    """클라이언트에 한 번만 보여주는 고엔트로피 원문 토큰."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """DB에 남기는 값. 원문으로 되돌리지 않는다."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
