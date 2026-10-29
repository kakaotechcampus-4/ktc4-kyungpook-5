"""행사 도메인의 결정론적 규칙 (NF1).

라우터·서비스는 이 모듈의 순수 함수 결과를 그대로 쓸 뿐, 판정을 직접 하거나
보정하지 않는다.
"""

from app.core.enums import ActionType

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
