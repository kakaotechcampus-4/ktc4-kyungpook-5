"""행사 도메인 오케스트레이션.

현재는 mock 단계다 (이슈 #30). DB가 없어 고정 fixture를 반환하며, 키는 실제
컬럼명(snake_case)에 맞춰 두었다. DB 연결 후에는 조회 함수 본문만 쿼리로
교체하면 라우터와 스키마는 그대로 쓴다.
"""

from datetime import UTC, date, datetime

from app.core.enums import ActionStatus, ActionType, MemberRole
from app.core.exceptions import EventNotFound

# fixture가 응답하는 유일한 행사. 다른 id는 EVENT_NOT_FOUND다.
MOCK_EVENT_ID = "evt_9f2c8a"

_MANAGER = {"id": "mbr_01", "name": "박수겸", "role": MemberRole.MANAGER}
_OWNER = {"id": "mbr_02", "name": "정하늘", "role": MemberRole.OWNER}


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# amount는 이슈 #30에서 전건 null로 합의했다. 컬럼은 존재하므로 값을 채우는 건
# FE가 금액 표시를 검증할 때 바꾸면 된다.
_ACTIONS: list[dict] = [
    {
        "id": "act_21",
        "type": ActionType.EXTERNAL_SEND,
        "title": "미납자 4명에게 2차 납부 안내 문자 발송",
        "subtitle": "대상 4명 · 비용 0원 · 마감 D-2",
        "irreversible": True,
        "approve_needed": True,
        "status": ActionStatus.PENDING,
        "amount": None,
        "due_date": date(2026, 3, 12),
        "step_id": "stp_03",
        "step_name": "입금 내역 확인",
        "resolved_at": None,
        "resolved_by": None,
        "deny_reason": None,
        "can_approve": True,
    },
    {
        "id": "act_22",
        "type": ActionType.TRANSFER,
        "title": "버스 대절 업체 A에 잔금 송금",
        "subtitle": "마감 D-1",
        "irreversible": True,
        "approve_needed": True,
        "status": ActionStatus.PENDING,
        "amount": None,
        "due_date": date(2026, 3, 13),
        "step_id": "stp_03",
        "step_name": "입금 내역 확인",
        "resolved_at": None,
        "resolved_by": None,
        "deny_reason": None,
        "can_approve": True,
    },
    {
        "id": "act_23",
        "type": ActionType.NOTICE,
        "title": "참가자 38명에게 집합 장소 공지",
        "subtitle": None,
        "irreversible": False,
        "approve_needed": True,
        "status": ActionStatus.PENDING,
        "amount": None,
        "due_date": None,
        "step_id": "stp_04",
        "step_name": "사전 안내",
        "resolved_at": None,
        "resolved_by": None,
        "deny_reason": None,
        "can_approve": True,
    },
    {
        # 단계에 묶이지 않는 확인 요청. excludeType=CONFIRMATION이면 빠진다.
        "id": "act_31",
        "type": ActionType.CONFIRMATION,
        "title": "숙소를 B펜션으로 변경할까요?",
        "subtitle": "A펜션이 예약 마감되었습니다",
        "irreversible": False,
        "approve_needed": True,
        "status": ActionStatus.PENDING,
        "amount": None,
        "due_date": None,
        "step_id": None,
        "step_name": None,
        "resolved_at": None,
        "resolved_by": None,
        "deny_reason": None,
        "can_approve": True,
    },
    {
        "id": "act_09",
        "type": ActionType.CONTRACT,
        "title": "버스 대절 업체 B와 계약",
        "subtitle": None,
        "irreversible": True,
        "approve_needed": True,
        "status": ActionStatus.DENIED,
        "amount": None,
        "due_date": None,
        "step_id": "stp_02",
        "step_name": "세부사항 조정",
        "resolved_at": _utc(2026, 3, 8, 8, 2),
        "resolved_by": _MANAGER,
        "deny_reason": "견적이 작년보다 40% 높아 다른 업체를 더 받아보기로 했습니다.",
        "can_approve": True,
    },
    {
        "id": "act_11",
        "type": ActionType.EXTERNAL_SEND,
        "title": "입금 12건을 참가자 명단과 대조했습니다",
        "subtitle": None,
        "irreversible": False,
        "approve_needed": False,
        "status": ActionStatus.DONE,
        "amount": None,
        "due_date": None,
        "step_id": "stp_03",
        "step_name": "입금 내역 확인",
        "resolved_at": _utc(2026, 3, 9, 1, 30),
        "resolved_by": None,
        "deny_reason": None,
        "can_approve": True,
    },
    {
        "id": "act_05",
        "type": ActionType.EXPENSE,
        "title": "펜션 예약금 지출 등록",
        "subtitle": None,
        "irreversible": True,
        "approve_needed": True,
        "status": ActionStatus.APPROVED,
        "amount": None,
        "due_date": None,
        "step_id": "stp_02",
        "step_name": "세부사항 조정",
        "resolved_at": _utc(2026, 3, 7, 23, 15),
        "resolved_by": _OWNER,
        "deny_reason": None,
        "can_approve": True,
    },
]


def list_actions(
    event_id: str,
    *,
    statuses: list[ActionStatus] | None = None,
    action_type: ActionType | None = None,
    exclude_type: ActionType | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """행사의 Action 목록과 전체 건수를 돌려준다.

    type과 exclude_type은 함께 쓰이지 않는다. 확인 요청만 보는 화면과 확인 요청만
    빼고 보는 화면이 둘 다 있어 파라미터가 두 개다.
    """
    if event_id != MOCK_EVENT_ID:
        raise EventNotFound

    rows = _ACTIONS
    if statuses:
        rows = [row for row in rows if row["status"] in statuses]
    if action_type is not None:
        rows = [row for row in rows if row["type"] == action_type]
    if exclude_type is not None:
        rows = [row for row in rows if row["type"] != exclude_type]

    total_count = len(rows)
    offset = (page - 1) * size
    return rows[offset : offset + size], total_count
