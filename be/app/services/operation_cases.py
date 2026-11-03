"""운영 상황 질문 및 답변 기반 제안. 외부 AI 호출 중 DB 잠금을 유지하지 않는다."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import ai
from app.core.deps import ensure_member
from app.core.enums import ActionStatus, ActionType, EventStatus
from app.core.exceptions import ApiError, EventNotFound, EventNotOnGoing, IdempotencyConflict
from app.models.auth import Account
from app.models.clubs import Member
from app.models.events import Action, Event
from app.models.operation_cases import OperationCase
from app.schemas.operation_cases import OperationCaseOut
from app.services import action_service, event_service

ATTEMPT_TIMEOUT = timedelta(minutes=3)


class CaseNotFound(ApiError):
    status_code = 404
    code = 'OPERATION_CASE_NOT_FOUND'
    def __init__(self):
        super().__init__('운영 상황을 찾을 수 없습니다.')


class CaseInProgress(ApiError):
    status_code = 409
    code = 'OPERATION_IN_PROGRESS'
    def __init__(self):
        super().__init__('처리 중입니다. 잠시 뒤 다시 확인해 주세요.')


class AnswerRequired(ApiError):
    status_code = 409
    code = 'OPERATION_ANSWER_REQUIRED'
    def __init__(self):
        super().__init__('확인 질문에 먼저 답해 주세요.')


def _expired(case: OperationCase) -> bool:
    return bool(case.attempt_started_at and datetime.now(UTC) - case.attempt_started_at >= ATTEMPT_TIMEOUT)


async def _fresh_member(session: AsyncSession, club_id: str, account: Account) -> Member:
    # 모델 호출 중 세션 identity map에 남은 이전 소속 상태를 덮어쓴다.
    await session.scalar(select(Member).where(Member.club_id == club_id, Member.account_id == account.id)
                         .with_for_update().execution_options(populate_existing=True))
    return await ensure_member(session, club_id=club_id, account=account)


async def get_case(session: AsyncSession, event_id: str, case_id: str, *, lock: bool = False) -> OperationCase:
    stmt = select(OperationCase).where(OperationCase.id == case_id, OperationCase.event_id == event_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    case = await session.scalar(stmt)
    if case is None:
        raise CaseNotFound()
    return case


async def render(session: AsyncSession, case: OperationCase, event: Event, member: Member) -> OperationCaseOut:
    action = None
    if case.action_id:
        row = await session.scalar(select(Action).where(Action.id == case.action_id, Action.event_id == event.id)
                                   .options(selectinload(Action.step), selectinload(Action.resolver)))
        if row:
            action = event_service.action_out(row, member=member, event_status=event.status)
    qstatus, rstatus, error = case.question_status, case.result_status, case.error_code
    if _expired(case):
        if qstatus == 'PROCESSING':
            qstatus, error = 'FAILED', 'OPERATION_TIMEOUT'
        if rstatus == 'PROCESSING':
            rstatus, error = 'FAILED', 'OPERATION_TIMEOUT'
    return OperationCaseOut.model_validate({
        'id': case.id, 'event_id': case.event_id, 'client_request_id': case.client_request_id,
        'situation': case.situation, 'question_status': qstatus, 'action': action,
        'result_status': rstatus, 'result': case.result,
        'error': {'code': error, 'message': '처리하지 못했습니다. 다시 시도해 주세요.'} if error else None,
        'created_at': case.created_at, 'modified_at': case.modified_at,
    })


async def create(session: AsyncSession, event: Event, member: Member, account: Account,
                 client_request_id: str, situation: str) -> OperationCase:
    event = await action_service.lock_operating_event(session, event.id)
    await _fresh_member(session, event.club_id, account)
    existing = await session.scalar(select(OperationCase).where(
        OperationCase.event_id == event.id, OperationCase.client_request_id == client_request_id))
    if existing:
        if existing.situation != situation:
            raise IdempotencyConflict()
        return existing
    case = OperationCase(event_id=event.id, client_request_id=client_request_id, situation=situation,
                         question_status='PENDING', result_status='NOT_REQUESTED')
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return await run(session, event.id, case.id, account, 'question')


async def run(session: AsyncSession, event_id: str, case_id: str, account: Account, stage: str) -> OperationCase:
    event = await action_service.lock_operating_event(session, event_id)
    await _fresh_member(session, event.club_id, account)
    case = await get_case(session, event_id, case_id, lock=True)
    if stage == 'question' and case.question_status in ('NEEDS_ANSWER', 'NO_QUESTION'):
        return case
    if stage == 'result' and case.result_status == 'READY':
        return case
    if (case.question_status == 'PROCESSING' or case.result_status == 'PROCESSING') and not _expired(case):
        raise CaseInProgress()
    answer = None
    question = None
    options = ()
    action_version = None
    if stage == 'result':
        if case.question_status != 'NEEDS_ANSWER' or not case.action_id:
            raise AnswerRequired()
        action = await session.get(Action, case.action_id)
        if action is None or action.event_id != event_id or action.status != ActionStatus.DONE:
            raise AnswerRequired()
        payload = action.payload or {}
        choice = payload.get('resolved_choice')
        answer = payload.get('manual_value') if choice == 'MANUAL' else next(
            (item['label'] for item in payload.get('options', []) if item.get('key') == choice), None)
        if not answer:
            raise AnswerRequired()
        question = action.content or action.title
        options = tuple(item['label'] for item in payload.get('options', []))
        action_version = action.version
    token = uuid4().hex
    case.attempt_id = token
    case.attempt_started_at = datetime.now(UTC)
    case.error_code = None
    if stage == 'question':
        case.question_status = 'PROCESSING'
    else:
        case.result_status = 'PROCESSING'
    try:
        request = ai.OperationalSituationRequest(
            event_context=ai.OperationalEventContext(title=event.title.strip() or '제목 미정', event_type=event.event_type,
                start_date=event.start_date, end_date=event.end_date, location=event.location,
                expected_headcount=event.expected_headcount),
            situation=case.situation, clarification_question=question, clarification_options=options, answer=answer)
    except ValidationError:
        case.error_code = 'AI_INVALID_INPUT'
        if stage == 'question': case.question_status = 'FAILED'
        else: case.result_status = 'FAILED'
        case.attempt_id = None
        case.attempt_started_at = None
        await session.commit()
        await session.refresh(case)
        return case
    await session.commit()
    try:
        generated = await ai.respond_operational_situation(request)
        failure = None
    except ai.AIError:
        generated = None
        failure = 'AI_UNAVAILABLE'
    event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update().execution_options(populate_existing=True))
    if event is None:
        raise EventNotFound()
    await _fresh_member(session, event.club_id, account)
    case = await get_case(session, event_id, case_id, lock=True)
    if case.attempt_id != token:
        return case
    if event.status != EventStatus.ON_GOING:
        case.error_code = 'EVENT_NOT_ON_GOING'
        if stage == 'question': case.question_status = 'FAILED'
        else: case.result_status = 'FAILED'
        case.attempt_id = None
        case.attempt_started_at = None
        await session.commit()
        raise EventNotOnGoing()
    if stage == 'result':
        action = await session.get(Action, case.action_id, populate_existing=True)
        if action is None or action.event_id != event_id or action.version != action_version or action.status != ActionStatus.DONE:
            failure = 'OPERATION_ANSWER_CHANGED'
    if stage == 'result' and generated is not None and generated.status != 'suggestion':
        failure = 'AI_INVALID_RESPONSE'
    if failure:
        case.error_code = failure
        if stage == 'question': case.question_status = 'FAILED'
        else: case.result_status = 'FAILED'
    elif generated.status == 'clarification':
        question = generated.question
        action = Action(event_id=event_id, step_id=None, type=ActionType.CONFIRMATION,
                        title=question[:200], content=question, irreversible=False, approve_needed=False,
                        status=ActionStatus.PENDING, payload={'options': [
                            {'key': f'OPTION_{i}', 'label': value} for i, value in enumerate(generated.options, 1)],
                            'allow_manual': True})
        session.add(action)
        await session.flush()
        case.action_id = action.id
        case.question_status = 'NEEDS_ANSWER'
    else:
        if stage == 'question': case.question_status = 'NO_QUESTION'
        case.result_status = 'READY'
        case.result = {'summary': generated.summary, 'suggestions': list(generated.suggestions)}
    case.attempt_id = None
    case.attempt_started_at = None
    await session.commit()
    await session.refresh(case)
    return case


async def list_cases(session: AsyncSession, event_id: str, page: int, size: int):
    total = await session.scalar(select(func.count()).select_from(OperationCase).where(OperationCase.event_id == event_id))
    rows = list(await session.scalars(select(OperationCase).where(OperationCase.event_id == event_id)
        .order_by(OperationCase.created_at.desc(), OperationCase.id.desc()).offset((page - 1) * size).limit(size)))
    return rows, total
