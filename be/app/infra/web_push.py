"""실제 RFC Web Push 전송. 동기 HTTP/암호화는 worker thread에서 수행한다."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class PushTarget:
    id: str
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushResult:
    accepted: bool
    error_code: str | None = None
    invalidated: bool = False


class PushTransport(Protocol):
    async def send(self, target: PushTarget, payload: dict[str, Any]) -> PushResult: ...


class WebPushTransport:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def send(self, target: PushTarget, payload: dict[str, Any]) -> PushResult:
        return await asyncio.to_thread(self._send_sync, target, payload)

    def _send_sync(self, target: PushTarget, payload: dict[str, Any]) -> PushResult:
        settings = self.settings
        private_key = settings.web_push_vapid_private_key.get_secret_value()
        if not (private_key and settings.web_push_vapid_subject):
            return PushResult(False, "PUSH_NOT_CONFIGURED")
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:
            return PushResult(False, "PUSH_TRANSPORT_UNAVAILABLE")
        try:
            response = webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=private_key,
                vapid_claims={"sub": settings.web_push_vapid_subject},
                ttl=settings.web_push_ttl_seconds,
                timeout=settings.web_push_timeout_seconds,
                content_encoding="aes128gcm",
            )
            if 200 <= response.status_code < 300:
                return PushResult(True)
            return PushResult(False, f"PUSH_HTTP_{response.status_code}", response.status_code in (404, 410))
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            status = response.status_code if response is not None else None
            code = f"PUSH_HTTP_{status}" if status else "PUSH_TRANSPORT_FAILED"
            return PushResult(False, code, status in (404, 410))
        except Exception:
            # 예외 본문에 endpoint·키가 들어갈 수 있으므로 저장·로그에 넣지 않는다.
            return PushResult(False, "PUSH_TRANSPORT_FAILED")
