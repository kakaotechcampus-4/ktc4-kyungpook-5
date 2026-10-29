"""행사 도메인의 결정론적 규칙 (NF1).

라우터·서비스는 이 모듈의 순수 함수 결과를 그대로 쓸 뿐, 판정을 직접 하거나
보정하지 않는다.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

from app.core.enums import ActionStatus, ActionType, MemberRole, StepState

# 되돌릴 수 없고(irreversible) 승인이 필요한(approve_needed) 외부 영향 행동.
# NF3: 공지·예약·송금·환불 등 외부에 영향을 주는 액션은 Approval 레코드가
# 승인 상태로 존재할 때만 실행한다.
_IRREVERSIBLE_AND_APPROVAL: frozenset[ActionType] = frozenset(
    {
        ActionType.EXTERNAL_SEND,
        ActionType.TRANSFER,
        ActionType.EXPENSE,
        ActionType.CONTRACT,
    }
)
# 되돌릴 수는 있지만 승인은 거쳐야 하는 행동.
_APPROVAL_ONLY: frozenset[ActionType] = frozenset({ActionType.NOTICE})


def action_defaults(action_type: ActionType) -> tuple[bool, bool]:
    """ActionType별 (irreversible, approve_needed) 기본값.

    CONFIRMATION은 확인만 하는 행동이라 되돌릴 것도 승인받을 것도 없다.
    """
    if action_type in _IRREVERSIBLE_AND_APPROVAL:
        return True, True
    if action_type in _APPROVAL_ONLY:
        return False, True
    return False, False


# 승인·거절·확인요청 응답을 할 수 있는 역할 (FE 명세 v1 — 승인·계획 변경은 운영진만).
_RESOLVER_ROLES: frozenset[MemberRole] = frozenset({MemberRole.OWNER, MemberRole.MANAGER})


def can_resolve(role: MemberRole, status: ActionStatus) -> bool:
    """이 역할이 지금 이 행동을 승인·거절·응답할 수 있는지.

    조회 응답의 canApprove와 승인 API의 권한 검사가 같이 쓴다. 둘이 따로 판정하면
    버튼은 보이는데 누르면 403이 나는 식으로 어긋난다.
    """
    return role in _RESOLVER_ROLES and status == ActionStatus.PENDING


def is_editable(status: ActionStatus) -> bool:
    """세부 내용을 고칠 수 있는지 (#106).

    APPROVED도 열어 둔다 — 고치면 services에서 PENDING으로 되돌려 재승인을 받는다.
    """
    return status in (ActionStatus.PENDING, ActionStatus.APPROVED)


class _StepLike(Protocol):
    id: str
    completed_at: datetime | None


def step_states(steps: Sequence[_StepLike]) -> dict[str, StepState]:
    """step_order 순으로 받은 단계의 진행 상태 (이슈 #17 판단 A).

    처음으로 completed_at이 비어 있는 단계가 CURRENT, 그 앞은 DONE, 뒤는 TODO다.
    """
    states: dict[str, StepState] = {}
    reached_current = False
    for step in steps:
        if reached_current:
            states[step.id] = StepState.TODO
        elif step.completed_at is None:
            states[step.id] = StepState.CURRENT
            reached_current = True
        else:
            states[step.id] = StepState.DONE
    return states


def dday(start_date: date | None, today: date) -> int | None:
    """행사 시작일까지 남은 날 수. 지난 행사는 음수다."""
    return (start_date - today).days if start_date else None
