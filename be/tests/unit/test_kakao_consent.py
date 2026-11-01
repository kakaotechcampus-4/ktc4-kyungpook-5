from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationFailed
from app.routers import auth


@pytest.mark.anyio
@pytest.mark.parametrize('account, field', [
    ({'email_needs_agreement': True}, 'emailConsent'),
    ({'email_needs_agreement': False}, 'email'),
])
async def test_missing_kakao_email_distinguishes_consent(monkeypatch, account, field):
    monkeypatch.setattr(auth, 'get_settings', lambda: SimpleNamespace(
        kakao_rest_api_key='key', kakao_redirect_uri='https://example.test/callback',
        kakao_client_secret=SimpleNamespace(get_secret_value=lambda: ''),
    ))

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {'access_token': 'token'})
        async def get(self, *args, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: {'id': 1, 'kakao_account': account})

    monkeypatch.setattr(auth.httpx, 'AsyncClient', Client)
    with pytest.raises(ValidationFailed) as exc:
        await auth._exchange_kakao_code('code')
    assert field in exc.value.fields
