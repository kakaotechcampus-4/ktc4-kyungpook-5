"""행사 도메인의 결정론적 규칙 (NF1).

라우터·서비스는 이 모듈의 순수 함수 결과를 그대로 쓸 뿐, 판정을 직접 하거나
보정하지 않는다.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Protocol

from app.core.enums import (
    SERVICE_ROLES,
    ActionContentSource,
    ActionContentStatus,
    ActionStatus,
    ActionType,
    EventStatus,
    MemberRole,
    StepState,
)

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


# 승인·거절·확인요청 응답을 할 수 있는 역할. 서비스 이용 대상(SERVICE_ROLES)과 같게 둬서
# 역할 정책이 바뀌면 조회 권한(ensure_member)과 canApprove가 함께 따라가게 한다.
_RESOLVER_ROLES: frozenset[MemberRole] = frozenset(SERVICE_ROLES)


def can_resolve(role: MemberRole, status: ActionStatus) -> bool:
    """이 역할이 지금 이 행동을 승인·거절·응답할 수 있는지.

    조회 응답의 canApprove와 승인 API의 권한 검사가 같이 쓴다. 둘이 따로 판정하면
    버튼은 보이는데 누르면 403이 나는 식으로 어긋난다.
    """
    return role in _RESOLVER_ROLES and status == ActionStatus.PENDING


def is_operating(event_status: EventStatus) -> bool:
    """승인·거절·실행 완료·단계 완료를 받는 행사 상태 (#177 — 운영 시작 후의 일).

    계획 중에는 다시 생성하면 행동이 새로 만들어지므로 처리하지 않는다. 취소 정리(CANCELLING)
    중 처리 여부는 #73에서 정한다.
    """
    return event_status == EventStatus.ON_GOING


def can_approve(
    role: MemberRole,
    status: ActionStatus,
    *,
    action_type: ActionType,
    approve_needed: bool,
    event_status: EventStatus,
) -> bool:
    """조회 응답의 canApprove. 처리 API가 받아들이는 조건과 같아야 한다.

    확인 요청은 /resolve로 답하고, 나머지는 승인이 필요한 행동만 /approve·/deny 대상이다.
    """
    return (
        can_resolve(role, status)
        and is_operating(event_status)
        and (is_confirmation(action_type) or approve_needed)
    )


def is_confirmation(action_type: ActionType) -> bool:
    """확인 요청은 승인·거절이 아니라 선택지를 고르는 행동이라 처리 경로가 다르다."""
    return action_type == ActionType.CONFIRMATION


def can_mark_done(status: ActionStatus, *, approve_needed: bool) -> bool:
    """운영진이 직접 실행을 마쳤다고 기록할 수 있는지 (#41).

    앱은 발송·이체를 대신하지 않는다. 승인을 받은 뒤(승인이 필요 없으면 바로) 운영진이
    실행하고 완료를 남긴다.
    """
    if status == ActionStatus.APPROVED:
        return True
    return status == ActionStatus.PENDING and not approve_needed


def is_step_done(action_statuses: Sequence[ActionStatus]) -> bool:
    """단계의 행동이 하나 이상 있고 모두 DONE이면 단계도 끝난 것이다 (FE 명세 v1).

    행동이 없는 MANUAL 단계는 사람이 직접 완료 처리하므로 자동으로 끝내지 않는다.
    """
    return bool(action_statuses) and all(s == ActionStatus.DONE for s in action_statuses)


def is_editable(status: ActionStatus) -> bool:
    """세부 내용을 고칠 수 있는지 (#106).

    APPROVED도 열어 둔다 — 고치면 services에서 PENDING으로 되돌려 재승인을 받는다.
    """
    return status in (ActionStatus.PENDING, ActionStatus.APPROVED)


def is_step_editable(completed_at: datetime | None) -> bool:
    """단계의 일정을 고칠 수 있는지 (#106 ③).

    끝난 단계는 결과 기록이라 건드리지 않는다. Action의 is_editable과 달리
    되돌릴 방법이 없어 APPROVED 같은 중간 상태가 없다.
    """
    return completed_at is None


# 본문 초안을 쓰는 Action 종류 (#334). 글로 내보내는 일이라 초안이 바로 쓸모 있다.
# 계약·송금·지출은 금액과 대상이 핵심이라 대상이 아니다.
DRAFT_ACTION_TYPES: frozenset[ActionType] = frozenset(
    {ActionType.NOTICE, ActionType.EXTERNAL_SEND}
)
# 이 시간이 지나도 DRAFTING이면 서버 재시작 등으로 멈춘 작성으로 본다
# (운영 상황 operation_cases.ATTEMPT_TIMEOUT과 같은 값).
DRAFT_TIMEOUT = timedelta(minutes=3)


def is_draft_stale(
    content_status: ActionContentStatus, draft_started_at: datetime | None, now: datetime
) -> bool:
    """멈춘 작성인지. DRAFTING이고 시작한 지 DRAFT_TIMEOUT이 지났으면 그렇다."""
    if content_status != ActionContentStatus.DRAFTING:
        return False
    return draft_started_at is None or now - draft_started_at >= DRAFT_TIMEOUT


def shown_content_status(
    content_status: ActionContentStatus, draft_started_at: datetime | None, now: datetime
) -> ActionContentStatus:
    """응답의 contentStatus. 멈춘 작성은 응답에서만 FAILED로 바꾼다(DB는 그대로)."""
    if is_draft_stale(content_status, draft_started_at, now):
        return ActionContentStatus.FAILED
    return content_status


def can_request_draft(
    *,
    event_status: EventStatus,
    action_status: ActionStatus,
    action_type: ActionType,
    content_status: ActionContentStatus,
    content_source: ActionContentSource | None,
    draft_started_at: datetime | None,
    now: datetime,
) -> bool:
    """「초안 다시 받기」를 받을 수 있는지. 응답의 canRequestDraft와 POST /draft가 같이 쓴다.

    운영 중, 승인 대기(PENDING), 대상 종류, 운영진이 고친 글이 아님, 작성 중이 아님(3분 넘게
    멈춘 작성은 허용). 한 번도 초안을 요청하지 않은 Action(NONE)은 "다시" 받을 것이 없어서
    제외한다 — 아직 현재 단계가 아닌 공지에 미리 초안을 쓰지 않는다.
    """
    if content_status == ActionContentStatus.NONE:
        return False
    if content_status == ActionContentStatus.DRAFTING and not is_draft_stale(
        content_status, draft_started_at, now
    ):
        return False
    return (
        is_operating(event_status)
        and action_status == ActionStatus.PENDING
        and action_type in DRAFT_ACTION_TYPES
        and content_source != ActionContentSource.USER
    )


class _StepLike(Protocol):
    id: str
    completed_at: datetime | None


def step_states(
    steps: Sequence[_StepLike], *, event_status: EventStatus
) -> dict[str, StepState]:
    """step_order 순으로 받은 단계의 진행 상태 (이슈 #17 판단 A).

    처음으로 completed_at이 비어 있는 단계가 CURRENT, 그 앞은 DONE, 뒤는 TODO다.
    계획 중(PLANNING)에는 단계 진행이 시작되지 않았으므로 모두 TODO다(#336).
    단계 진행은 운영 시작 뒤의 일이다(is_operating, #177).
    """
    if event_status == EventStatus.PLANNING:
        return {step.id: StepState.TODO for step in steps}
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
