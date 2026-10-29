"""실제 Push 어댑터의 암호화 라이브러리 계약·오류·입력 검증."""

import base64
import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infra.web_push import PushTarget, WebPushTransport
from app.schemas.push import PushSubscriptionIn


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _subscription(endpoint: str = "https://fcm.googleapis.com/fcm/send/device") -> dict:
    return {"endpoint": endpoint, "expirationTime": None,
            "keys": {"p256dh": _b64(b"\x04" + b"x" * 64), "auth": _b64(b"a" * 16)}}


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/a",
    "https://127.0.0.1/internal", "https://example.com/push",
    "https://fcm.googleapis.com.evil.invalid/push",
    "https://user:password@fcm.googleapis.com/push",
    "https://fcm.googleapis.com:8080/push",
])
def test_untrusted_push_endpoints_are_rejected(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        PushSubscriptionIn.model_validate(_subscription(endpoint))


def test_browser_json_is_accepted_and_bad_keys_are_rejected() -> None:
    body = _subscription()
    assert PushSubscriptionIn.model_validate(body).expiration_time is None
    body["keys"]["auth"] = "short"
    with pytest.raises(ValidationError):
        PushSubscriptionIn.model_validate(body)


class FakePushException(Exception):
    def __init__(self, status: int) -> None:
        self.response = SimpleNamespace(status_code=status)


def _settings() -> Settings:
    return Settings(
        _env_file=None, web_push_vapid_private_key="private-value",
        web_push_vapid_subject="mailto:admin@example.com",
        web_push_vapid_public_key="public-value",
    )


def _target() -> PushTarget:
    body = _subscription()
    return PushTarget("psh_device", body["endpoint"], body["keys"]["p256dh"], body["keys"]["auth"])


@pytest.mark.anyio
async def test_transport_sends_encrypted_vapid_and_reports_service_acceptance(monkeypatch) -> None:
    calls = []

    def webpush(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=201)

    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(
        webpush=webpush, WebPushException=FakePushException
    ))
    result = await WebPushTransport(_settings()).send(_target(), {"title": "회의 알림"})
    assert result.accepted and not result.invalidated
    assert json.loads(calls[0]["data"])["title"] == "회의 알림"
    assert calls[0]["vapid_claims"] == {"sub": "mailto:admin@example.com"}
    assert calls[0]["vapid_private_key"] == "private-value"
    assert calls[0]["content_encoding"] == "aes128gcm"
    assert calls[0]["timeout"] > 0


@pytest.mark.anyio
@pytest.mark.parametrize("status,invalidated", [(404, True), (410, True), (401, False), (503, False)])
async def test_transport_invalidates_only_gone_subscription_statuses(monkeypatch, status, invalidated) -> None:
    def webpush(**kwargs):
        raise FakePushException(status)

    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(
        webpush=webpush, WebPushException=FakePushException
    ))
    result = await WebPushTransport(_settings()).send(_target(), {"title": "알림"})
    assert not result.accepted
    assert result.error_code == f"PUSH_HTTP_{status}"
    assert result.invalidated is invalidated


@pytest.mark.anyio
async def test_missing_config_is_explicit_and_does_not_call_transport(monkeypatch) -> None:
    settings = Settings(_env_file=None, web_push_vapid_private_key="", web_push_vapid_subject="")
    result = await WebPushTransport(settings).send(_target(), {})
    assert not result.accepted and result.error_code == "PUSH_NOT_CONFIGURED"


@pytest.mark.anyio
async def test_real_library_encrypts_and_signs_before_http_boundary(monkeypatch) -> None:
    """암호화·VAPID는 실제 라이브러리로 수행하고 HTTP 호출만 막는다."""
    import requests
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    vapid_key = ec.generate_private_key(ec.SECP256R1())
    recipient_key = ec.generate_private_key(ec.SECP256R1())
    raw_private = vapid_key.private_numbers().private_value.to_bytes(32, "big")
    recipient_public = recipient_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    settings = _settings()
    from pydantic import SecretStr
    settings.web_push_vapid_private_key = SecretStr(_b64(raw_private))
    target = PushTarget("psh_crypto", "https://fcm.googleapis.com/fcm/send/crypto",
                        _b64(recipient_public), _b64(b"a" * 16))
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=201, text="", headers={}, reason="Created")

    monkeypatch.setattr(requests, "post", post)
    result = await WebPushTransport(settings).send(target, {"title": "plaintext-marker"})
    assert result.accepted
    assert len(calls) == 1
    request = calls[0][1]
    assert b"plaintext-marker" not in request["data"]
    assert request["headers"]["content-encoding"] == "aes128gcm"
    assert request["headers"]["Authorization"].startswith("vapid t=")
