"""opaque Bearer로 로그인한 자신의 기기 구독만 관리·테스트한다."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_service_account
from app.db.session import get_session
from app.models.auth import Account
from app.schemas.common import Envelope
from app.schemas.push import (
    PushDeleteOut, PushDispatchOut, PushPublicKeyOut, PushSubscriptionIn,
    PushSubscriptionOut, PushTestIn,
)
from app.services import push_service

router = APIRouter(prefix="/api/v1/push", tags=["push"])


@router.get("/vapid-public-key", response_model=Envelope[PushPublicKeyOut])
async def vapid_public_key(
    _account: Account = Depends(require_service_account),
) -> Envelope[PushPublicKeyOut]:
    return Envelope(data=PushPublicKeyOut(public_key=push_service.public_key()))


@router.get("/subscriptions", response_model=Envelope[list[PushSubscriptionOut]])
async def list_own_subscriptions(
    account: Account = Depends(require_service_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[list[PushSubscriptionOut]]:
    items = await push_service.list_subscriptions(session, account_id=account.id)
    return Envelope(data=[PushSubscriptionOut.model_validate(item) for item in items])


@router.post("/subscriptions", response_model=Envelope[PushSubscriptionOut], status_code=201)
async def subscribe(
    body: PushSubscriptionIn,
    account: Account = Depends(require_service_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PushSubscriptionOut]:
    item = await push_service.register_subscription(session, account_id=account.id, body=body)
    return Envelope(data=PushSubscriptionOut.model_validate(item))


@router.delete("/subscriptions/{subscription_id}", response_model=Envelope[PushDeleteOut])
async def unsubscribe(
    subscription_id: str,
    account: Account = Depends(require_service_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PushDeleteOut]:
    await push_service.delete_subscription(session, account_id=account.id, subscription_id=subscription_id)
    return Envelope(data=PushDeleteOut(id=subscription_id, deleted=True))


@router.post("/test", response_model=Envelope[PushDispatchOut])
async def send_test_push(
    body: PushTestIn,
    account: Account = Depends(require_service_account),
    session: AsyncSession = Depends(get_session),
) -> Envelope[PushDispatchOut]:
    """SERVICE_ACCEPTED는 Push 서비스 접수이며 실제 기기 표시 확인은 별도로 한다."""
    result = await push_service.test_push(
        session, account_id=account.id, subscription_id=body.subscription_id,
    )
    return Envelope(data=result)
