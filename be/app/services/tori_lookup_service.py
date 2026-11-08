"""토리 답 카드에 쓰는 조회: 행사·회의를 이름으로 찾기, 행사 현황, 승인 대기, 회의별 할 일.

분류기는 발화 속 이름만 그대로 넘긴다(예: "봄 MT"). 어느 행사·회의인지는 여기서 정한다.
권한 확인(동아리 소속)은 라우터가 먼저 끝낸 뒤 부른다.
"""

import re
from collections.abc import Sequence
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import EventStatus, MeetingStatus, StepState
from app.models.accounting import Expense
from app.models.agent import ContextDecision
from app.models.events import Action, Event, Step
from app.models.meetings import Meeting
from app.models.reminders import ConfirmedTask
from app.models.tasks import TaskSuggestion
from app.services import event_service

KST = ZoneInfo('Asia/Seoul')
Found = Literal['found', 'choose', 'missing']
# 되물을 때 보여 줄 후보 수. 더 많으면 이름을 더 알려 달라고 한다.
CHOICE_LIMIT = 5
APPROVAL_TITLE_LIMIT = 5
MEETING_TASK_LIMIT = 50


def _norm(text: str) -> str:
    return re.sub(r'[^0-9a-z가-힣]', '', text.lower())


def _narrow_by_name(rows: Sequence, key: str, title) -> list:
    """이름이 정확히 같은 것이 있으면 그것만, 없으면 이름에 서로 포함되는 것을 남긴다.

    정확히 같은 이름을 먼저 보는 이유: "봄 MT"와 "2026 봄 MT"가 함께 있을 때 되묻기 버튼
    "봄 MT 어디까지 됐어?"를 누르면 다시 둘 다 맞아 되묻기가 끝나지 않는다.
    """
    exact = [row for row in rows if _norm(title(row)) == key]
    if exact:
        return exact
    return [row for row in rows if key in _norm(title(row)) or _norm(title(row)) in key]


async def resolve_event(session: AsyncSession, *, club_id: str, target: str | None) -> tuple[Found, list[Event]]:
    """발화 속 행사 이름으로 행사를 찾는다.

    - 하나만 맞으면 그 행사
    - 여러 개면 진행 중인 행사가 하나뿐일 때 그 행사, 아니면 후보를 돌려 되묻는다
    - 이름이 없으면 진행 중이거나 계획 중인 행사 안에서 같은 규칙을 쓴다
    """
    events = list(await session.scalars(
        select(Event).where(Event.club_id == club_id)
        .options(selectinload(Event.steps))
        # 같은 이름만 남았을 때 가장 최근 행사를 고르도록 최근 순으로 둔다.
        .order_by(Event.start_date.desc().nulls_last(), Event.created_at.desc(), Event.id)
    ))
    key = re.sub(r'행사$', '', _norm(target)) if target else ''
    if key:
        candidates = _narrow_by_name(events, key, lambda event: event.title)
    else:
        candidates = [event for event in events if event.status in (EventStatus.ON_GOING, EventStatus.PLANNING)]
    if not candidates:
        return 'missing', []
    if len(candidates) == 1:
        return 'found', candidates
    ongoing = [event for event in candidates if event.status == EventStatus.ON_GOING]
    if len(ongoing) == 1:
        return 'found', ongoing
    pool = ongoing or candidates
    if len({_norm(event.title) for event in pool}) == 1:
        # 해마다 같은 이름으로 여는 행사는 이름으로 구분할 수 없어 가장 최근 것을 본다.
        return 'found', pool[:1]
    # 고를 때는 행사 목록처럼 시작일이 가까운 순으로 보여 준다.
    return 'choose', sorted(pool, key=lambda event: (event.start_date is None, event.start_date or date.max))


async def event_status_card(session: AsyncSession, event: Event) -> dict:
    """행사 현황 카드: 지금 단계와 다음 단계 둘, 승인 대기, 예산 대비 지출."""
    card = (await event_service.event_cards(session, [event]))[0]
    steps = await event_service.list_steps(session, event_id=event.id, event_status=event.status)
    index = next((i for i, step in enumerate(steps) if step['state'] == StepState.CURRENT), None)

    def step_out(step: dict) -> dict:
        deadline = step['deadline']
        return {'name': step['name'], 'due_date': deadline.astimezone(KST).date() if deadline else None}

    approvals = list(await session.scalars(
        select(Action.title)
        .where(Action.event_id == event.id, *event_service.PENDING_APPROVAL)
        .order_by(*event_service.ACTION_ORDER)
    ))
    spent = await session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.event_id == event.id)
    )
    return {
        'type': 'event_status',
        'event': card,
        'current_step': step_out(steps[index]) if index is not None else None,
        'next_steps': [step_out(step) for step in steps[index + 1:index + 3]] if index is not None else [],
        'approvals': approvals[:APPROVAL_TITLE_LIMIT],
        'approval_count': len(approvals),
        'budget': event.budget_total,
        'spent': spent or 0,
    }


async def approval_groups(session: AsyncSession, *, club_id: str, event_id: str | None = None) -> list[dict]:
    """운영 중 행사의 승인 대기를 행사별로 묶는다. 브리핑·행사 카드의 승인 대기 수와 같은 기준이다."""
    conditions = [Event.club_id == club_id, Event.status == EventStatus.ON_GOING, *event_service.PENDING_APPROVAL]
    if event_id is not None:
        conditions.append(Action.event_id == event_id)
    rows = await session.execute(
        select(Action, Event.title, Step.name)
        .join(Event, Action.event_id == Event.id)
        .outerjoin(Step, Action.step_id == Step.id)
        .where(*conditions)
        .order_by(Event.start_date.asc().nulls_last(), Event.id, *event_service.ACTION_ORDER)
    )
    groups: dict[str, dict] = {}
    for action, event_title, step_name in rows.tuples():
        group = groups.setdefault(action.event_id, {
            'event_id': action.event_id, 'event_title': event_title, 'actions': [],
        })
        group['actions'].append({
            'id': action.id, 'title': action.title, 'step_name': step_name, 'due_date': action.due_date,
        })
    return list(groups.values())


def meeting_label(meeting: Meeting) -> str:
    """화면에 쓰는 회의 이름. 제목이 없으면 "11/5 회의"처럼 날짜로 부른다."""
    if meeting.title and meeting.title.strip():
        return meeting.title.strip()
    day = _meeting_day(meeting)
    return f'{day.month}/{day.day} 회의'


def _meeting_day(meeting: Meeting) -> date:
    return (meeting.started_at or meeting.created_at).astimezone(KST).date()


async def resolve_meeting(session: AsyncSession, *, club_id: str, target: str | None,
                          meeting_date: date | None) -> tuple[Found, list[Meeting]]:
    """회의 이름·날짜로 회의를 찾는다. 둘 다 없으면("지난 회의") 녹음이 끝난 가장 최근 회의다."""
    when = func.coalesce(Meeting.started_at, Meeting.created_at)
    meetings = list(await session.scalars(
        select(Meeting).where(Meeting.club_id == club_id).order_by(when.desc(), Meeting.id.desc()).limit(200)
    ))
    key = re.sub(r'회의$', '', _norm(target)) if target else ''
    if not key and meeting_date is None:
        latest = [meeting for meeting in meetings if meeting.status != MeetingStatus.RECORDING]
        return ('found', latest[:1]) if latest else ('missing', [])
    candidates = meetings
    if meeting_date is not None:
        candidates = [meeting for meeting in candidates if _meeting_day(meeting) == meeting_date]
    if key:
        named = _narrow_by_name(candidates, key, lambda meeting: meeting.title or '')
        # 날짜가 맞는 회의가 있으면 이름이 달라도 날짜를 더 믿는다("10월 15일 운영회의" ↔ 제목 "정기 회의").
        candidates = named or (candidates if meeting_date is not None else [])
    if not candidates:
        return 'missing', []
    if len(candidates) == 1 or len({(_meeting_day(m), _norm(m.title or '')) for m in candidates}) == 1:
        return 'found', candidates[:1]
    return 'choose', candidates


def meeting_ask(meeting: Meeting) -> str:
    """되묻기 버튼 문장. 날짜를 앞에 붙여 다시 물었을 때 한 회의로 좁혀지게 한다."""
    day = _meeting_day(meeting)
    name = meeting.title.strip() if meeting.title and meeting.title.strip() else '회의'
    return f'{day.month}월 {day.day}일 {name}에서 정한 할 일'


async def meeting_tasks_card(session: AsyncSession, *, club_id: str, meeting: Meeting) -> dict:
    """회의에서 확정한 할 일·일정. 할 일 → 할 일 후보 → 회의 판단 → 회의로 이어 찾는다."""
    item_time = func.coalesce(ConfirmedTask.due_at, ConfirmedTask.scheduled_at)
    rows = list(await session.scalars(
        select(ConfirmedTask)
        .join(TaskSuggestion, ConfirmedTask.suggestion_id == TaskSuggestion.id)
        .join(ContextDecision, TaskSuggestion.decision_id == ContextDecision.id)
        .where(ConfirmedTask.club_id == club_id, ConfirmedTask.status == 'ACTIVE',
               ContextDecision.meeting_id == meeting.id)
        .order_by(item_time.asc().nulls_last(), ConfirmedTask.created_at, ConfirmedTask.id)
        .limit(MEETING_TASK_LIMIT + 1)
    ))
    tasks = []
    for task in rows[:MEETING_TASK_LIMIT]:
        when = task.due_at or task.scheduled_at
        tasks.append({
            'id': task.id, 'title': task.title, 'kind': task.kind, 'assignee_name': task.assignee_name,
            'due_date': when.astimezone(KST).date() if when else None,
        })
    return {
        'type': 'tasks',
        'title': f'{meeting_label(meeting)}에서 정한 할 일',
        'meeting_id': meeting.id,
        'tasks': tasks,
        'has_more': len(rows) > MEETING_TASK_LIMIT,
    }
