"""회의에서 권한 범위 내 행사 사실을 조회한다."""

from sqlalchemy import select

from app import ai
from app.core.enums import EventStatus
from app.db.session import get_sessionmaker
from app.models.events import Event


async def answer(payload: dict):
    request = ai.JudgeUtteranceRequest.model_validate(payload)
    classified = await ai.classify_meeting_event_facts(request)
    intent = classified.intent
    if intent.disposition == 'none':
        return None, classified.trace
    if intent.disposition == 'clarify':
        return {'answer': '어떤 행사와 정보를 확인할지 알려 주세요.', 'citations': []}, classified.trace

    stmt = select(Event).where(Event.club_id == payload['club_id'])
    if intent.scope == 'current':
        stmt = stmt.where(Event.status == EventStatus.ON_GOING)
    elif intent.scope == 'recent':
        stmt = stmt.where(Event.status == EventStatus.COMPLETE)
    else:
        stmt = stmt.where(Event.title == intent.event_reference)
    stmt = stmt.order_by(Event.start_date.desc().nullslast(), Event.id).limit(21)
    async with get_sessionmaker()() as session:
        rows = list(await session.scalars(stmt))
        events = tuple(ai.MeetingEventFact(
            event_id=row.id, title=row.title, status=row.status, start_date=row.start_date,
            end_date=row.end_date, location=row.location, expected_headcount=row.expected_headcount,
            actual_headcount=None,
        ) for row in rows[:20])
    result = ai.answer_meeting_event_facts(ai.MeetingEventFactsRequest(
        scope=intent.scope, fields=intent.fields, events=events,
        complete=len(rows) <= 20, latest_verified=False,
    ))
    titles = {event.event_id: event.title for event in events}
    return {'answer': result.answer, 'citations': [
        {'type': 'event', 'eventId': event_id, 'title': titles[event_id]}
        for event_id in result.event_ids
    ]}, classified.trace
