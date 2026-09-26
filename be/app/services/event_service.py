"""행사 도메인 오케스트레이션.

현재는 mock 단계다 (이슈 #30). DB가 없어 고정 fixture를 반환하며, 키는 실제
컬럼명(snake_case)에 맞춰 두었다. DB 연결 후에는 조회 함수 본문만 쿼리로
교체하면 라우터와 스키마는 그대로 쓴다.
"""

from datetime import UTC, date, datetime

from app.core.enums import (
    ActionStatus,
    ActionType,
    EventStatus,
    MemberRole,
    StepActor,
    StepState,
)
from app.core.exceptions import EventNotFound

# fixture가 응답하는 유일한 행사. 다른 id는 EVENT_NOT_FOUND다.
MOCK_EVENT_ID = "evt_9f2c8a"

# dday·상태 계산의 기준일. 실제 시계 대신 fixture 날짜들과 맞춘 고정값이다.
_TODAY = date(2026, 3, 10)

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
        "payload": None,
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
        "payload": None,
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
        "payload": None,
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
        "payload": {
            "options": [
                {"key": "CHANGE_B", "label": "B펜션으로 변경"},
                {"key": "KEEP_A", "label": "A펜션 유지"},
            ],
            "allow_manual": True,
        },
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
        "payload": None,
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
        "payload": None,
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
        "payload": None,
        "step_id": "stp_02",
        "step_name": "세부사항 조정",
        "resolved_at": _utc(2026, 3, 7, 23, 15),
        "resolved_by": _OWNER,
        "deny_reason": None,
        "can_approve": True,
    },
]

_EVENTS: list[dict] = [
    {
        "id": MOCK_EVENT_ID,
        "club_id": "clb_3a71c0",
        "title": "2026 봄 MT",
        "status": EventStatus.ON_GOING,
        "start_date": date(2026, 3, 21),
        "end_date": date(2026, 3, 22),
    },
]

# step_id는 _ACTIONS의 step_id와 맞춘다. completed_at 유무로 state(DONE/CURRENT/TODO)를
# 계산하므로(이슈 #17 판단 A), 여기 값만 바꾸면 진행 상황이 바뀐다.
_STEPS: list[dict] = [
    {
        "id": "stp_01",
        "step_order": 10,
        "name": "사전 조사",
        "actor": StepActor.AI,
        "started_time": _utc(2026, 3, 5, 0, 0),
        "deadline": None,
        "completed_at": _utc(2026, 3, 6, 10, 0),
    },
    {
        "id": "stp_02",
        "step_order": 20,
        "name": "세부사항 조정",
        "actor": StepActor.APPROVAL_REQUIRED,
        "started_time": _utc(2026, 3, 6, 10, 0),
        "deadline": None,
        "completed_at": _utc(2026, 3, 9, 9, 0),
    },
    {
        "id": "stp_03",
        "step_order": 30,
        "name": "입금 내역 확인",
        "actor": StepActor.AI,
        "started_time": _utc(2026, 3, 10, 0, 0),
        "deadline": _utc(2026, 3, 12, 14, 59),
        "completed_at": None,
    },
    {
        "id": "stp_04",
        "step_order": 40,
        "name": "사전 안내",
        "actor": StepActor.MANUAL,
        "started_time": None,
        "deadline": None,
        "completed_at": None,
    },
]


def _step_states(steps: list[dict]) -> dict[str, StepState]:
    """이전 단계가 전부 completed_at 있으면 DONE, 처음 없는 곳이 CURRENT, 그 뒤는 TODO."""
    states: dict[str, StepState] = {}
    reached_current = False
    for step in sorted(steps, key=lambda s: s["step_order"]):
        if reached_current:
            states[step["id"]] = StepState.TODO
        elif step["completed_at"] is None:
            states[step["id"]] = StepState.CURRENT
            reached_current = True
        else:
            states[step["id"]] = StepState.DONE
    return states


def _expand_payload(row: dict) -> dict:
    """CONFIRMATION 선택지는 payload(JSONB)에 들어 있다. 응답 평탄화는 여기서만 한다."""
    payload = row["payload"] or {}
    return {
        **row,
        "options": payload.get("options"),
        "allow_manual": payload.get("allow_manual"),
    }


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
    return [_expand_payload(row) for row in rows[offset : offset + size]], total_count


def _pending_approval_count(event_id: str) -> int:
    """M1 카드와 같은 기준(PENDING, CONFIRMATION 제외)으로 센다.

    지금은 fixture 전체가 한 행사(evt_9f2c8a) 소속이라 event_id로 걸러도 결과는
    같지만, DB 연결 후 쿼리로 바꿀 때 시그니처가 바뀌지 않도록 미리 받아둔다.
    """
    return len(
        [
            row
            for row in _ACTIONS
            if row["status"] == ActionStatus.PENDING
            and row["type"] != ActionType.CONFIRMATION
        ]
        if event_id == MOCK_EVENT_ID
        else []
    )


def list_events(
    *,
    club_id: str | None = None,
    status: EventStatus | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict], int]:
    """행사 목록과 전체 건수를 돌려준다."""
    rows = _EVENTS
    if club_id is not None:
        rows = [row for row in rows if row["club_id"] == club_id]
    if status is not None:
        rows = [row for row in rows if row["status"] == status]

    total_count = len(rows)
    offset = (page - 1) * size
    page_rows = rows[offset : offset + size]

    states = _step_states(_STEPS)
    ordered_steps = sorted(_STEPS, key=lambda s: s["step_order"])
    current_step = next(
        (s for s in ordered_steps if states[s["id"]] == StepState.CURRENT), None
    )
    step_progress = [
        {"step_order": s["step_order"], "state": states[s["id"]]} for s in ordered_steps
    ]

    result = [
        {
            "id": row["id"],
            "title": row["title"],
            "status": row["status"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "dday": (row["start_date"] - _TODAY).days if row["start_date"] else None,
            "current_step_name": current_step["name"] if current_step else None,
            "step_progress": step_progress,
            "pending_approval_count": _pending_approval_count(row["id"]),
            "payment": None,
            "budget": None,
        }
        for row in page_rows
    ]
    return result, total_count


def list_steps(event_id: str) -> list[dict]:
    """행사의 Step 목록을 step_order 순으로 돌려준다."""
    if event_id != MOCK_EVENT_ID:
        raise EventNotFound

    ordered_steps = sorted(_STEPS, key=lambda s: s["step_order"])
    states = _step_states(ordered_steps)

    result = []
    for step in ordered_steps:
        step_actions = [row for row in _ACTIONS if row["step_id"] == step["id"]]
        done_actions = [row for row in step_actions if row["status"] == ActionStatus.DONE]
        remaining_actions = [
            row
            for row in step_actions
            if row["status"] in (ActionStatus.PENDING, ActionStatus.APPROVED)
        ]
        result.append(
            {
                **step,
                "state": states[step["id"]],
                "completed_count": len(done_actions),
                "total_action_count": len(step_actions),
                "done_actions": done_actions,
                "remaining_actions": remaining_actions,
            }
        )
    return result
