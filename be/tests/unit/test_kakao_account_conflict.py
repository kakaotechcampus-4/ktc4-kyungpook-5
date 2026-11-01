from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ValidationFailed
from app.services.auth_service import login_with_kakao
from app.services import auth_service


@pytest.mark.anyio
async def test_kakao_does_not_take_over_existing_email_account():
    existing = SimpleNamespace(kakao_user_id=None)
    session = SimpleNamespace(scalar=AsyncMock(side_effect=[None, existing]))

    with pytest.raises(ValidationFailed) as exc:
        await login_with_kakao(session, kakao_user_id='123', email='user@example.com')

    assert 'kakaoConflict' in exc.value.fields
    assert existing.kakao_user_id is None


@pytest.mark.anyio
@pytest.mark.parametrize('existing', [None, SimpleNamespace(kakao_user_id='123')])
async def test_kakao_creates_or_reuses_its_account(monkeypatch, existing):
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[existing] if existing else [None, None]),
        add=lambda account: None,
        flush=AsyncMock(), commit=AsyncMock(),
    )
    issue = AsyncMock(return_value=('access', 'refresh'))
    monkeypatch.setattr(auth_service, '_issue_session', issue)

    assert await login_with_kakao(session, kakao_user_id='123', email='user@example.com') == ('access', 'refresh')
    assert issue.call_args.args[1].kakao_user_id == '123'
    session.commit.assert_awaited_once()
