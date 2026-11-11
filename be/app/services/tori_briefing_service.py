"""메인 탭 브리핑: 오늘 확인할 일과 진행 중·계획 중 행사.

확인할 일은 세 가지를 모아 급한 순서로 돌려준다.
- 단계 마감: 운영 중 행사에서 끝나지 않은 단계 중 마감이 3일 안인 것(이미 지난 것 포함)
- 승인 대기: 운영 중 행사의 승인 대기 행동. 행사마다 한 줄로 묶고 나머지는 more_count로 센다
- 내 할 일: 이 계정에 배정된 확정 할 일 전부

권한 확인(동아리 소속)은 라우터가 먼저 끝낸 뒤 부른다.
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventStatus
from app.models.agent import ContextDecision
from app.models.events import Event, Step
from app.models.meetings import Meeting
from app.models.reminders import ConfirmedTask
from app.models.tasks import TaskSuggestion
from app.services import event_service, tori_lookup_service
from app.services.tori_lookup_service import KST, meeting_label

DEADLINE_DAYS = 3
# 배정된 할 일이 아주 많아도 화면 한 번에 쓸 만큼만 읽는다.
TASK_LIMIT = 50
APPROVAL_ASK = "승인 기다리는 거 보여줘"


def _kst_date(value: datetime) -> date:
    return value.astimezone(KST).date()


async def _deadline_items(session: AsyncSession, club_id: str, today: date) -> list[dict]:
    end = datetime.combine(today + timedelta(days=DEADLINE_DAYS + 1), time.min, KST)
    rows = await session.execute(
        select(Step, Event.title)
        .join(Event, Step.event_id == Event.id)
        .where(
            Event.club_id == club_id,
            Event.status == EventStatus.ON_GOING,
            Step.completed_at.is_(None),
            Step.deadline.is_not(None),
            Step.deadline < end,
        )
        .order_by(Step.deadline, Step.step_order, Step.id)
    )
    return [
        {
            "id": f"deadline:{step.id}",
            "kind": "deadline",
            "title": f"{step.name} 단계 마감",
            "source": event_title,
            "due_date": _kst_date(step.deadline),
            "more_count": 0,
            "event_id": step.event_id,
            "ask": f"{event_title} 어디까지 됐어?",
        }
        for step, event_title in rows.tuples()
    ]


async def _approval_items(session: AsyncSession, club_id: str) -> list[dict]:
    items = []
    for group in await tori_lookup_service.approval_groups(session, club_id=club_id):
        # 행사 안에서는 마감이 가까운 행동이 앞에 온다(event_service.ACTION_ORDER).
        first, *rest = group["actions"]
        title = group["event_title"]
        items.append(
            {
                "id": f"approval:{group['event_id']}",
                "kind": "approval",
                "title": first["title"],
                "source": f"{title} | {first['step_name']} 단계" if first["step_name"] else title,
                "due_date": first["due_date"],
                "more_count": len(rest),
                "event_id": group["event_id"],
                "ask": APPROVAL_ASK,
            }
        )
    return items


async def _task_items(session: AsyncSession, club_id: str, account_id: str) -> list[dict]:
    rows = await session.execute(
        select(ConfirmedTask, Meeting)
        .join(TaskSuggestion, ConfirmedTask.suggestion_id == TaskSuggestion.id)
        .join(ContextDecision, TaskSuggestion.decision_id == ContextDecision.id)
        .outerjoin(Meeting, ContextDecision.meeting_id == Meeting.id)
        .where(
            ConfirmedTask.club_id == club_id,
            ConfirmedTask.status == "ACTIVE",
            ConfirmedTask.kind == "TASK",
            ConfirmedTask.assignee_account_id == account_id,
        )
        .order_by(ConfirmedTask.due_at.asc().nulls_last(), ConfirmedTask.created_at, ConfirmedTask.id)
        .limit(TASK_LIMIT)
    )
    items = []
    for task, meeting in rows.tuples():
        label = meeting_label(meeting) if meeting else None
        items.append(
            {
                "id": f"task:{task.id}",
                "kind": "task",
                "title": task.title,
                "source": label or "확정한 할 일",
                "due_date": _kst_date(task.due_at) if task.due_at else None,
                "more_count": 0,
                "task_id": task.id,
                "meeting_id": meeting.id if meeting else None,
                "ask": f"{label}에서 정한 할 일" if label else None,
            }
        )
    return items


def _urgency(item: dict, today: date) -> tuple:
    """오늘 마감(지난 것 포함) → 기한 없는 승인 대기 → 내일 이후 날짜순 → 기한 없는 할 일."""
    due: date | None = item["due_date"]
    if due is not None and due <= today:
        return (0, due)
    if due is None and item["kind"] == "approval":
        return (1, date.min)
    if due is not None:
        return (2, due)
    return (3, date.min)


def sort_items(items: Sequence[dict], today: date) -> list[dict]:
    # sorted는 안정 정렬이라 같은 순위 안에서는 단계 → 승인 → 할 일 순서가 유지된다.
    return sorted(items, key=lambda item: _urgency(item, today))


async def build_briefing(session: AsyncSession, *, club_id: str, account_id: str) -> dict:
    today = event_service.today_kst()
    items = [
        *await _deadline_items(session, club_id, today),
        *await _approval_items(session, club_id),
        *await _task_items(session, club_id, account_id),
    ]
    events = []
    for status in (EventStatus.ON_GOING, EventStatus.PLANNING):
        rows, _total = await event_service.list_events(
            session, club_id=club_id, status=status, page=1, size=20
        )
        events.extend(rows)
    return {"items": sort_items(items, today), "events": events}

