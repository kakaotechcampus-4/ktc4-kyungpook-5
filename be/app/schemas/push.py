"""브라우저 PushSubscription.toJSON 입력과 계정별 구독 메타데이터."""

import base64
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from app.schemas.common import CamelModel, UtcDateTime


def validate_push_endpoint(value: str) -> str:
    """사용자가 준 URL로 내부망에 요청하지 않고 알려진 브라우저 Push 서비스만 쓴다."""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    allowed = (
        host == "fcm.googleapis.com"
        or host == "updates.push.services.mozilla.com"
        or host.endswith(".push.services.mozilla.com")
        or host == "web.push.apple.com"
        or host.endswith(".notify.windows.com")
    )
    if (
        parsed.scheme != "https" or not allowed or parsed.port not in (None, 443)
        or parsed.username or parsed.password or parsed.fragment or not parsed.path
    ):
        raise ValueError("지원하는 브라우저의 HTTPS Push 구독 주소가 필요합니다.")
    return value


def _validate_key(value: str, length: int) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("올바른 base64url 구독 키가 필요합니다.")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("올바른 base64url 구독 키가 필요합니다.") from exc
    if len(decoded) != length or (length == 65 and decoded[0] != 4):
        raise ValueError("구독 키 길이 또는 형식이 올바르지 않습니다.")
    return value


class PushKeysIn(CamelModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)

    @field_validator("p256dh")
    @classmethod
    def valid_p256dh(cls, value: str) -> str:
        return _validate_key(value, 65)

    @field_validator("auth")
    @classmethod
    def valid_auth(cls, value: str) -> str:
        return _validate_key(value, 16)


class PushSubscriptionIn(CamelModel):
    endpoint: str = Field(min_length=1, max_length=4096)
    keys: PushKeysIn
    # 브라우저 표준은 Unix milliseconds 또는 null이다.
    expiration_time: float | None = Field(default=None, gt=0)

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        return validate_push_endpoint(value)

    @field_validator("expiration_time")
    @classmethod
    def valid_expiration(cls, value: float | None) -> float | None:
        if value is not None:
            try:
                expires = datetime.fromtimestamp(value / 1000, UTC)
            except (ValueError, OverflowError, OSError) as exc:
                raise ValueError("유효한 구독 만료 시각이 필요합니다.") from exc
            if expires <= datetime.now(UTC):
                raise ValueError("만료된 구독입니다. 브라우저에서 다시 구독해 주세요.")
        return value


class PushSubscriptionOut(CamelModel):
    id: str
    active: bool
    expiration_time: UtcDateTime | None
    last_used_at: UtcDateTime | None
    last_error: str | None
    created_at: UtcDateTime


class PushPublicKeyOut(CamelModel):
    public_key: str


class PushDeleteOut(CamelModel):
    id: str
    deleted: bool


class PushTestIn(CamelModel):
    subscription_id: str | None = Field(default=None, max_length=26)


class PushFailureOut(CamelModel):
    subscription_id: str
    code: str


class PushDispatchOut(CamelModel):
    # SERVICE_ACCEPTED는 기기 수신/표시를 확인했다는 뜻이 아니다.
    status: Literal["SERVICE_ACCEPTED", "PARTIAL_FAILURE", "FAILED"]
    accepted_count: int
    failed_count: int
    invalidated_count: int
    failures: list[PushFailureOut]
