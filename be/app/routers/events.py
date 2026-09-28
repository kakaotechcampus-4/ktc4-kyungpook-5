"""행사 관련 엔드포인트."""

from fastapi import APIRouter, Query

from app.core.enums import ActionStatus, ActionType, EventStatus
from app.core.exceptions import ValidationFailed
from app.schemas.events import ActionListResponse, EventListResponse, StepListResponse
from app.services import event_service

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=EventListResponse)
def list_events(
    club_id: str | None = Query(None, alias="clubId"),
    status: EventStatus | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> EventListResponse:
    rows, total_count = event_service.list_events(
        club_id=club_id, status=status, page=page, size=size
    )
    return EventListResponse.model_validate(
        {"data": rows, "meta": {"page": page, "size": size, "total_count": total_count}}
    )


def _parse_statuses(raw: str | None) -> list[ActionStatus] | None:
    """status=PENDING 과 status=APPROVED,DONE,DENIED 를 모두 받는다.

    enum 목록을 쉼표로 받는 형태라 FastAPI가 직접 검증해주지 못해 여기서 본다.
    """
    if raw is None:
        return None
    codes = [code.strip() for code in raw.split(",") if code.strip()]
    try:
        return [ActionStatus(code) for code in codes]
    except ValueError:
        allowed = ", ".join(ActionStatus)
        raise ValidationFailed({"status": f"허용되는 값: {allowed}"}) from None


@router.get("/{event_id}/actions", response_model=ActionListResponse)
def list_event_actions(
    event_id: str,
    status: str | None = Query(
        None, description="쉼표로 여러 개. 예: PENDING, APPROVED,DONE,DENIED"
    ),
    type: ActionType | None = Query(None, description="이 유형만 조회"),
    exclude_type: ActionType | None = Query(
        None, alias="excludeType", description="이 유형만 제외"
    ),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> ActionListResponse:
    rows, total_count = event_service.list_actions(
        event_id,
        statuses=_parse_statuses(status),
        action_type=type,
        exclude_type=exclude_type,
        page=page,
        size=size,
    )
    return ActionListResponse.model_validate(
        {"data": rows, "meta": {"page": page, "size": size, "total_count": total_count}}
    )


@router.get("/{event_id}/steps", response_model=StepListResponse)
def list_event_steps(event_id: str) -> StepListResponse:
    rows = event_service.list_steps(event_id)
    return StepListResponse.model_validate({"data": rows, "meta": None})
