"""event_rules 순수 함수 테스트 (#41, #187)."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from app.core.enums import ActionStatus, ActionType, MemberRole, StepState
from app.services import event_rules


@pytest.mark.parametrize(
    ("role", "status", "expected"),
    [
        (MemberRole.OWNER, ActionStatus.PENDING, True),
        (MemberRole.MANAGER, ActionStatus.PENDING, True),
        (MemberRole.MEMBER, ActionStatus.PENDING, False),
        (MemberRole.OWNER, ActionStatus.APPROVED, False),
        (MemberRole.OWNER, ActionStatus.DONE, False),
        (MemberRole.OWNER, ActionStatus.DENIED, False),
    ],
)
def test_운영진만_대기_중인_행동을_처리할_수_있다(
    role: MemberRole, status: ActionStatus, expected: bool
) -> None:
    assert event_rules.can_resolve(role, status) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ActionStatus.PENDING, True),
        (ActionStatus.APPROVED, True),
        (ActionStatus.DONE, False),
        (ActionStatus.DENIED, False),
        (ActionStatus.FAILED, False),
    ],
)
def test_대기와_승인된_행동만_고칠_수_있다(status: ActionStatus, expected: bool) -> None:
    assert event_rules.is_editable(status) is expected


@dataclass
class _Step:
    id: str
    completed_at: datetime | None


def test_처음으로_안_끝난_단계가_현재_단계다() -> None:
    done = datetime(2026, 3, 1, tzinfo=UTC)
    steps = [_Step("a", done), _Step("b", None), _Step("c", done), _Step("d", None)]

    # 현재 단계 뒤는 completed_at이 있어도 TODO다.
    assert event_rules.step_states(steps) == {
        "a": StepState.DONE,
        "b": StepState.CURRENT,
        "c": StepState.TODO,
        "d": StepState.TODO,
    }


def test_단계가_모두_끝나면_현재_단계가_없다() -> None:
    done = datetime(2026, 3, 1, tzinfo=UTC)

    states = event_rules.step_states([_Step("a", done), _Step("b", done)])

    assert StepState.CURRENT not in states.values()


def test_dday는_시작일까지_남은_날이고_날짜가_없으면_null이다() -> None:
    today = date(2026, 3, 10)

    assert event_rules.dday(date(2026, 3, 21), today) == 11
    assert event_rules.dday(date(2026, 3, 9), today) == -1
    assert event_rules.dday(None, today) is None


def test_확인_요청은_승인도_되돌릴_것도_없다() -> None:
    assert event_rules.action_defaults(ActionType.CONFIRMATION) == (False, False)
    assert event_rules.action_defaults(ActionType.TRANSFER) == (True, True)
    assert event_rules.action_defaults(ActionType.NOTICE) == (False, True)
