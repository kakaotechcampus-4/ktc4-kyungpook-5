"""인증된 소속의 토리 대화."""
from datetime import UTC, date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.core.deps import get_current_account, require_member
from app.core.enums import EventStatus, RecordParseStatus
from app.core.exceptions import AIMisconfigured, AIUnavailable
from app.db.session import get_session
from app.models.auth import Account
from app.models.clubs import Member
from app.models.records import Record
from app.models.reminders import ConfirmedTask
from app.schemas.common import Envelope
from app.schemas.reminders import ConfirmedTaskOut
from app.schemas.tori import (
    ToriBriefingOut, ToriClarification, ToriEventsCard, ToriMessageIn, ToriMessageOut, ToriRecordAnswer,
)
from app.services import event_service, record_discovery_service, tori_briefing_service, tori_lookup_service

router = APIRouter(prefix='/api/v1/clubs/{club_id}/tori', tags=['tori'])
TZ = ZoneInfo('Asia/Seoul')


def _status_ask(title: str) -> str:
    return f'{title} 어디까지 됐어?'


async def _starters(session: AsyncSession, club_id: str) -> list[str]:
    """답하지 못했거나 되물을 때 바로 이어 물을 수 있는 말. 지금 데이터로 답이 나오는 것만 고른다."""
    suggestions = ['확인할 일 전부 보여줘']
    if await tori_lookup_service.approval_groups(session, club_id=club_id):
        suggestions.append(tori_briefing_service.APPROVAL_ASK)
    ongoing, _ = await event_service.list_events(session, club_id=club_id, status=EventStatus.ON_GOING, page=1, size=1)
    if ongoing:
        suggestions.append(_status_ask(ongoing[0]['title']))
    return suggestions


async def _lookup_reply(session: AsyncSession, *, club_id: str, account_id: str,
                        result: ai.ToriIntentResult) -> ToriMessageOut:
    """브리핑·승인 대기·행사 현황·회의 할 일. 모델 없이 DB 조회만 하고 카드로 답한다."""
    intent = result.intent
    if intent == 'briefing':
        briefing = await tori_briefing_service.build_briefing(session, club_id=club_id, account_id=account_id)
        items = briefing['items']
        if not items:
            return ToriMessageOut(intent=intent, reply='오늘 확인할 일이 없어요.')
        suggestions = [tori_briefing_service.APPROVAL_ASK] if any(i['kind'] == 'approval' for i in items) else []
        return ToriMessageOut(intent=intent, reply=f'오늘 확인할 일 {len(items)}개를 급한 순서로 모았어요.',
                              card={'type': 'briefing', 'items': items}, suggestions=suggestions)

    if intent in ('event_status', 'approval_list'):
        event = None
        if intent == 'event_status' or result.target:
            found, events = await tori_lookup_service.resolve_event(session, club_id=club_id, target=result.target)
            if found == 'missing':
                ongoing, _ = await event_service.list_events(
                    session, club_id=club_id, status=EventStatus.ON_GOING, page=1, size=20)
                reply = (f"'{result.target}' 행사를 찾지 못했어요." if result.target
                         else '진행 중이거나 계획 중인 행사가 없어요.')
                if ongoing:
                    reply += ' 진행 중인 행사는 이렇게 있어요.'
                return ToriMessageOut(
                    intent=intent, reply=reply,
                    card={'type': 'events', 'events': ongoing, 'total': len(ongoing)} if ongoing else None)
            if found == 'choose':
                # 후보를 버튼으로 보여 주고, 누르면 정확한 행사 이름으로 다시 묻게 한다.
                ask = _status_ask if intent == 'event_status' else (lambda title: f'{title} 승인 기다리는 거 보여줘')
                more = len(events) > tori_lookup_service.CHOICE_LIMIT
                return ToriMessageOut(
                    intent=intent,
                    reply=('어느 행사요? 비슷한 이름의 행사가 많아요. 이름을 조금 더 정확히 알려 주세요.' if more
                           else f'어느 행사요? 맞는 행사가 {len(events)}개 있어요.'),
                    suggestions=[ask(e.title) for e in events[:tori_lookup_service.CHOICE_LIMIT]])
            event = events[0]
        if intent == 'event_status':
            card = await tori_lookup_service.event_status_card(session, event)
            reply = {
                EventStatus.PLANNING: f'{event.title}, 아직 계획 중이에요. 운영을 시작하면 단계 진행을 볼 수 있어요.',
                EventStatus.COMPLETE: f'{event.title}, 끝난 행사예요.',
                EventStatus.CANCELLING: f'{event.title}, 취소를 정리하고 있어요.',
                EventStatus.CANCELLED: f'{event.title}, 취소된 행사예요.',
            }.get(event.status)
            if reply is None:
                current = card['current_step']
                reply = (f"{event.title}, 지금 {current['name']} 단계를 진행하고 있어요." if current
                         else f'{event.title}, 모든 단계를 마쳤어요.')
                if card['approval_count']:
                    reply += f" 승인을 기다리는 일이 {card['approval_count']}건 있어요."
            others, _ = await event_service.list_events(
                session, club_id=club_id, status=EventStatus.ON_GOING, page=1, size=3)
            suggestions = [tori_briefing_service.APPROVAL_ASK] if card['approval_count'] else []
            suggestions += [_status_ask(other['title']) for other in others if other['id'] != event.id][:2]
            return ToriMessageOut(intent=intent, reply=reply, card=card, suggestions=suggestions)
        groups = await tori_lookup_service.approval_groups(
            session, club_id=club_id, event_id=event.id if event else None)
        total = sum(len(group['actions']) for group in groups)
        where = f'{event.title}에서 ' if event else ''
        if not total:
            return ToriMessageOut(intent=intent, reply=f'{where}승인을 기다리는 일이 없어요.')
        return ToriMessageOut(
            intent=intent, reply=f'{where}승인을 기다리는 일이 {total}건 있어요. 행사 상세에서 내용을 보고 승인할 수 있어요.',
            card={'type': 'approvals', 'groups': groups},
            suggestions=[_status_ask(group['event_title']) for group in groups][:2])

    if intent == 'meeting_tasks':
        found, meetings = await tori_lookup_service.resolve_meeting(
            session, club_id=club_id, target=result.target, meeting_date=result.meeting_date)
        if found == 'missing':
            if result.target is None and result.meeting_date is None:
                return ToriMessageOut(intent=intent, reply='아직 끝난 회의가 없어요.')
            name = result.target or f'{result.meeting_date.month}월 {result.meeting_date.day}일'
            return ToriMessageOut(intent=intent, reply=f"'{name}' 회의를 찾지 못했어요.")
        if found == 'choose':
            return ToriMessageOut(
                intent=intent, reply=f'어느 회의요? 맞는 회의가 {len(meetings)}개 있어요.',
                suggestions=[tori_lookup_service.meeting_ask(m) for m in meetings[:tori_lookup_service.CHOICE_LIMIT]])
        meeting = meetings[0]
        card = await tori_lookup_service.meeting_tasks_card(session, club_id=club_id, meeting=meeting)
        label = tori_lookup_service.meeting_label(meeting)
        if not card['tasks']:
            return ToriMessageOut(intent=intent, reply=f'{label}에서 확정한 할 일이 없어요. 할 일 후보는 회의 화면에서 확인할 수 있어요.')
        today = event_service.today_kst()
        overdue = sum(1 for task in card['tasks']
                      if task['kind'] == 'TASK' and task['due_date'] and task['due_date'] < today)
        reply = f"{label}에서 확정한 할 일이 {len(card['tasks'])}{'개 넘게' if card['has_more'] else '개'} 있어요."
        if overdue:
            reply += f' 마감이 지난 일이 {overdue}개 있어요.'
        return ToriMessageOut(intent=intent, reply=reply, card=card)
    raise ValueError(f'카드 조회 분류가 아닙니다: {intent}')


def _task_list_reply(result: ai.ToriIntentResult, rows: list[ConfirmedTask], has_more: bool) -> str:
    """내 할 일 답의 한 줄. 목록은 카드가 보이므로 수와 오늘 마감만 말한다."""
    label = ('내 ' if result.scope == 'self' else '팀 ') + {
        'task': '할 일', 'schedule': '일정', 'all': '할 일과 일정'}[result.kind]
    if not rows:
        return f'이 기간에 확정한 {label}이 없어요.'
    reply = f"{label}이 {len(rows)}개{' 넘게' if has_more else ''} 있어요."
    today = datetime.now(TZ).date()
    due_today = sum(1 for row in rows if row.kind == 'TASK' and row.due_at and row.due_at.astimezone(TZ).date() == today)
    if due_today:
        reply += f' 오늘 마감인 일이 {due_today}개 있어요.'
    return reply


def _clear_clarification_choice(message: str, options: list[str], today: date) -> bool:
    """명시적 선택만 인정한다. 애매한 답을 특정 행사로 좁히지 않는다."""
    if not options:
        return True  # 예전 originalQuestion-only 요청은 기존 모델 처리 경로를 유지한다.
    text = re.sub(r'[^0-9가-힣a-z]', '', message.lower())
    if any(word in text for word in ('전체', '모두', '전부')):
        return True
    if re.fullmatch(r'(?:제)?(?:첫번째|첫째|두번째|둘째|세번째|셋째|[123]번?)(?:요|이요|로|으로)?', text):
        return True
    normalized_options = [re.sub(r'[^0-9가-힣a-z]', '', option.lower()) for option in options]
    matches = [option for option in normalized_options if len(text) >= 2 and len(option) >= 2
               and (text in option or option in text)]
    if len(matches) == 1:
        return True
    explicit_years = set(re.findall(r'(?:19|20)\d{2}', text))
    for word, year in (('재작년', today.year - 2), ('작년', today.year - 1), ('올해', today.year)):
        if word in text:
            explicit_years.add(str(year))
            break
    if explicit_years:
        if len(explicit_years) > 1:
            return True
        return sum(any(year in option for year in explicit_years) for option in normalized_options) <= 1
    return len(matches) == 1


@router.get('/briefing', response_model=Envelope[ToriBriefingOut])
async def briefing(club_id: str,
                   _member: Member = Depends(require_member),
                   account: Account = Depends(get_current_account),
                   session: AsyncSession = Depends(get_session)) -> Envelope[ToriBriefingOut]:
    """메인 탭 첫 화면의 오늘 확인할 일과 진행 중·계획 중 행사. 모델을 부르지 않는다."""
    data = await tori_briefing_service.build_briefing(session, club_id=club_id, account_id=account.id)
    return Envelope(data=ToriBriefingOut.model_validate(data))


@router.post('/messages', response_model=Envelope[ToriMessageOut])
async def message(club_id: str, body: ToriMessageIn,
                  _member: Member = Depends(require_member),
                  account: Account = Depends(get_current_account),
                  session: AsyncSession = Depends(get_session)) -> Envelope[ToriMessageOut]:
    # 권한 확인 뒤 모델 호출 중 DB 연결을 점유하지 않는다.
    await session.commit()
    context = body.clarification_context
    follow_up = None
    question = body.message
    try:
        if context is not None:
            resolution = await ai.build_tori_record_query(ai.ToriRecordQueryRequest(
                question=context.original_question, follow_up=body.message,
                clarification_question=context.question, clarification_options=tuple(context.options)))
            if resolution.disposition == 'follow_up':
                question = context.original_question
                follow_up = body.message
                result = ai.ToriIntentResult(intent='record_search', query=resolution.query)
            else:
                result = await ai.classify_tori_intent(ai.ToriIntentRequest(
                    message=body.message, reference_date=datetime.now(TZ).date(), timezone='Asia/Seoul'))
        else:
            result = await ai.classify_tori_intent(ai.ToriIntentRequest(
                message=body.message, reference_date=datetime.now(TZ).date(), timezone='Asia/Seoul'))
    except ai.AIConfigError as error:
        raise AIMisconfigured() from error
    except ai.AIError as error:
        raise AIUnavailable() from error
    # 외부 호출 중 권한이 바뀔 수 있어 조회 전에 다시 검증한다.
    from app.core.deps import ensure_member
    await ensure_member(session, club_id=club_id, account=account)
    ambiguous_follow_up = (context is not None and follow_up is not None
                           and not _clear_clarification_choice(follow_up, context.options, datetime.now(TZ).date()))
    if ambiguous_follow_up:
        # 알 수 없는 선택을 모델이 임의 연도로 좁히지 않도록 원질문 범위를 요약한다.
        result = ai.ToriIntentResult(intent='record_search', query=question[:200].strip())
    if result.intent == 'record_search':
        if not result.query or not result.query.strip() or len(result.query) > 200:
            if follow_up is not None:
                raise AIUnavailable()
            return Envelope(data=ToriMessageOut(intent='clarify', reply='찾을 자료를 조금 더 짧게 알려 주세요.'))
        chunks: list[ai.RetrievedChunk] = []
        lexical: list[ai.RetrievedChunk] = []
        lexical_omitted: list[bool] = []
        filename_only: list[str] = []
        records, total = await record_discovery_service.search_records(
            session, club_id=club_id, query=result.query.strip(), page=1, size=20,
            chunks_out=chunks, lexical_out=lexical, lexical_omitted=lexical_omitted,
            filename_only_out=filename_only)
        await ensure_member(session, club_id=club_id, account=account)
        if chunks:
            ids = {chunk.source.record_id for chunk in chunks}
            current = set((await session.scalars(select(Record.id).where(
                Record.id.in_(ids), Record.club_id == club_id,
                Record.parse_status == RecordParseStatus.INDEXED))).all())
            chunks = [chunk for chunk in chunks if chunk.source.record_id in current]
        if lexical:
            ids = {chunk.source.record_id for chunk in lexical}
            rows = list(await session.scalars(select(Record).where(
                Record.id.in_(ids), Record.club_id == club_id,
                Record.parse_status.in_((RecordParseStatus.COMPLETED, RecordParseStatus.INDEXED)))
                .execution_options(populate_existing=True)))
            allowed_blocks = {
                (record.id, record.file_name, block.get('location', {}).get('label'), block.get('text'))
                for record in rows for block in (record.parse_result or {}).get('blocks', [])
                if isinstance(block, dict) and isinstance(block.get('location'), dict)
            }
            lexical = [chunk for chunk in lexical if (
                chunk.source.record_id, chunk.source.file_name, chunk.source.location.label, chunk.text
            ) in allowed_blocks]
        semantic_capped = len(chunks) >= records['semantic_candidate_limit']
        seen = {(chunk.source.record_id, chunk.source.location.label, chunk.text) for chunk in lexical}
        selected_semantic = [chunk for chunk in chunks if (
            chunk.source.record_id, chunk.source.location.label, chunk.text
        ) not in seen][:record_discovery_service.SEMANTIC_LIMIT - len(lexical)]
        semantic_ids = {chunk.source.record_id for chunk in selected_semantic}
        chunks = lexical + selected_semantic
        answer_info = dict(
            semantic_status=records['semantic_status'],
            unindexed_count=records['unindexed_count'],
            searched_chunk_count=len(chunks),
            candidate_limit=records['semantic_candidate_limit'],
            candidate_limit_reached=semantic_capped or len(chunks) >= records['semantic_candidate_limit'],
            lexical_chunk_count=len(lexical),
            lexical_omitted=bool(lexical_omitted and lexical_omitted[0]),
            filename_only_unanalyzed_count=len(set(filename_only) - {
                chunk.source.record_id for chunk in chunks
            }),
        )
        clarification = None
        if records['semantic_status'] == 'UNAVAILABLE' and not chunks:
            answer = ToriRecordAnswer(status='failed', **answer_info)
        elif not chunks:
            answer = ToriRecordAnswer(status='insufficient', **answer_info)
        else:
            await session.commit()
            try:
                generated = await ai.answer_tori_records(ai.ToriRecordAnswerRequest(
                    question=question, follow_up=follow_up,
                    clarification_question=context.question if follow_up is not None else None,
                    clarification_options=tuple(context.options) if follow_up is not None else (),
                    clarification_allowed=follow_up is None,
                    today=datetime.now(TZ).date(), chunks=tuple(chunks)))
            except ai.AIError:
                answer = ToriRecordAnswer(status='failed', **answer_info)
            else:
                allowed = {chunk.source for chunk in chunks}
                facts = [*generated.facts, *(value for conflict in generated.conflicts for value in conflict.values)]
                def fact_out(fact):
                    return {'text': fact.content, 'sources': [source.model_dump() for source in fact.sources]}
                if generated.status == 'clarification':
                    if follow_up is not None:
                        answer = ToriRecordAnswer(status='failed', **answer_info)
                    else:
                        limited = (answer_info['semantic_status'] != 'AVAILABLE'
                                   or answer_info['unindexed_count'] > 0
                                   or answer_info['candidate_limit_reached']
                                   or answer_info['lexical_omitted']
                                   or answer_info['filename_only_unanalyzed_count'] > 0)
                        try:
                            if not generated.clarification_question or not generated.clarification_question.strip():
                                raise ValueError('명확화 질문이 비어 있습니다')
                            clarification = ToriClarification(
                                original_question=question,
                                question=('현재 확인한 자료 기준으로, ' if limited else '')
                                + generated.clarification_question,
                                options=list(generated.clarification_options))
                        except (ValidationError, ValueError):
                            answer = ToriRecordAnswer(status='failed', **answer_info)
                        else:
                            answer = ToriRecordAnswer(status='insufficient', **answer_info)
                elif any(source not in allowed for fact in facts for source in fact.sources):
                    answer = ToriRecordAnswer(status='failed', **answer_info)
                else:
                    answer = ToriRecordAnswer(
                        status=('insufficient' if generated.status == 'no_evidence' else
                                'partial' if generated.status == 'answered' and
                                records['semantic_status'] == 'UNAVAILABLE' else generated.status),
                        facts=[fact_out(fact) for fact in generated.facts],
                        conflicts=[{'description': conflict.description,
                                    'values': [fact_out(value) for value in conflict.values]}
                                   for conflict in generated.conflicts],
                        not_found=list(generated.not_found), **answer_info)
        await ensure_member(session, club_id=club_id, account=account)
        if chunks:
            ids = {chunk.source.record_id for chunk in chunks}
            rows = list(await session.scalars(select(Record).where(
                Record.id.in_(ids), Record.club_id == club_id,
                Record.parse_status.in_((RecordParseStatus.COMPLETED, RecordParseStatus.INDEXED)))
                .execution_options(populate_existing=True)))
            current = {record.id for record in rows}
            indexed_ids = {record.id for record in rows if record.parse_status == RecordParseStatus.INDEXED}
            if ids != current or not semantic_ids.issubset(indexed_ids):
                answer = ToriRecordAnswer(status='failed', **answer_info)
                clarification = None
            elif lexical:
                current_blocks = {
                    (record.id, record.file_name, block.get('location', {}).get('label'), block.get('text'))
                    for record in rows for block in (record.parse_result or {}).get('blocks', [])
                    if isinstance(block, dict) and isinstance(block.get('location'), dict)
                }
                if any((chunk.source.record_id, chunk.source.file_name,
                        chunk.source.location.label, chunk.text) not in current_blocks for chunk in lexical):
                    answer = ToriRecordAnswer(status='failed', **answer_info)
                    clarification = None
        item_ids = {item.id for item in records['items']}
        if item_ids:
            current_items = set((await session.scalars(select(Record.id).where(
                Record.id.in_(item_ids), Record.club_id == club_id))).all())
            records['items'] = [item for item in records['items'] if item.id in current_items]
        if clarification is not None:
            return Envelope(data=ToriMessageOut(intent='record_search', reply=clarification.question,
                                                 clarification=clarification))
        reply = {'answered': '자료에서 확인한 내용이에요.', 'partial': '자료에서 일부 내용을 확인했어요.',
                 'insufficient': '검색한 자료에서 답의 근거를 충분히 찾지 못했어요.',
                 'failed': '자료 답변을 만들지 못했어요. 검색 결과를 확인해 주세요.'}[answer.status]
        if ambiguous_follow_up:
            reply = '행사나 연도를 특정하지 않고 원래 질문의 자료 범위를 살펴봤어요. ' + reply
        return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply, record_answer=answer,
                                             records=records, record_total_count=total))
    if result.intent == 'task_list':
        if result.scope is None or result.kind is None:
            return Envelope(data=ToriMessageOut(intent='clarify', reply='누구의 일정이나 할 일을 찾을지 알려 주세요.'))
        if result.date_to == date.max:
            return Envelope(data=ToriMessageOut(intent='clarify', reply='조회할 날짜 범위를 다시 알려 주세요.'))
        item_time = func.coalesce(ConfirmedTask.due_at, ConfirmedTask.scheduled_at)
        stmt = select(ConfirmedTask).where(ConfirmedTask.club_id == club_id, ConfirmedTask.status == 'ACTIVE')
        if result.scope == 'self':
            stmt = stmt.where(ConfirmedTask.assignee_account_id == account.id)
        if result.kind != 'all':
            stmt = stmt.where(ConfirmedTask.kind == result.kind.upper())
        if result.date_from:
            stmt = stmt.where(item_time >= datetime.combine(result.date_from, time.min, TZ).astimezone(UTC))
        if result.date_to:
            end = datetime.combine(result.date_to + timedelta(days=1), time.min, TZ).astimezone(UTC)
            stmt = stmt.where(item_time < end)
        rows = list((await session.scalars(stmt.order_by(item_time, ConfirmedTask.id).limit(21))).all())
        tasks = {'items': [ConfirmedTaskOut.model_validate(row) for row in rows[:20]],
                 'has_more': len(rows) > 20, 'scope': result.scope, 'kind': result.kind,
                 'date_from': result.date_from.isoformat() if result.date_from else None,
                 'date_to': result.date_to.isoformat() if result.date_to else None}
        return Envelope(data=ToriMessageOut(intent=result.intent, reply=_task_list_reply(result, rows[:20], len(rows) > 20),
                                             tasks=tasks))
    if result.intent in ('briefing', 'approval_list', 'event_status', 'meeting_tasks'):
        return Envelope(data=await _lookup_reply(session, club_id=club_id, account_id=account.id, result=result))
    if result.intent == 'event_list':
        status = EventStatus(result.event_status) if result.event_status else None
        events, total = await event_service.list_events(session, club_id=club_id, status=status, page=1, size=20)
        labels = {'PLANNING': '계획 중인', 'ON_GOING': '진행 중인', 'COMPLETE': '끝난',
                  'CANCELLING': '취소 중인', 'CANCELLED': '취소된'}
        label = labels[status.value] + ' ' if status else ''
        if not events:
            reply = f'{label}행사가 없어요.'
        elif total > len(events):
            reply = f'{label}행사 {total}개 중 {len(events)}개를 보여드릴게요. 나머지는 행사 화면에서 볼 수 있어요.'
        else:
            reply = f'{label}행사 {total}개예요.'
        card = ToriEventsCard(events=events, total=total) if events else None
        return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply, card=card))
    if result.intent == 'event_planning':
        return Envelope(data=ToriMessageOut(
            intent=result.intent,
            reply='행사 계획은 계획 화면에서 토리와 이어서 정해요. 지금 말씀하신 내용을 들고 넘어갈게요.',
            card={'type': 'handoff', 'message': body.message}, navigation='/planning'))
    if result.intent == 'meeting':
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='회의 화면으로 이동할 수 있어요.', navigation='/meetings'))
    if result.intent == 'unsupported' and result.redirect == 'event_detail':
        # 실행은 하지 않고, 사람이 승인하러 갈 곳과 지금 기다리는 승인을 함께 보여 준다.
        groups = await tori_lookup_service.approval_groups(session, club_id=club_id)
        total = sum(len(group['actions']) for group in groups)
        reply = '발송, 승인, 이체는 제가 바로 하지 않아요. 행사 상세에서 운영진이 승인하면 그때 진행돼요.'
        if total:
            reply += f' 지금 승인을 기다리는 일이 {total}건 있어요.'
        return Envelope(data=ToriMessageOut(
            intent=result.intent, reply=reply,
            card={'type': 'approvals', 'groups': groups} if groups else None,
            suggestions=[_status_ask(group['event_title']) for group in groups][:2]))
    if result.intent == 'unsupported' and result.redirect is not None:
        reply, navigation = {
            'meetings': ('할 일 수정과 알림 예약은 제가 바로 하지 않아요. 회의 화면의 확정한 할 일에서 바꿀 수 있어요.', '/meetings'),
            'records': ('자료 수정과 삭제는 제가 바로 하지 않아요. 자료 화면에서 할 수 있어요.', '/records'),
            'accounting': ('지출 기록은 제가 바로 하지 않아요. 회계 화면에서 남길 수 있어요.', '/accounting'),
        }[result.redirect]
        return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply, navigation=navigation))
    reply = {
        'self_intro': ('저는 동아리 운영진과 함께 일하는 친근한 도우미 토리예요. '
                       '행사 진행 상황, 승인을 기다리는 일, 확정된 할 일을 모아 보여 드리고, '
                       '동아리 자료에서 지난 기록도 찾아 드려요. 행사 계획은 계획 화면으로 이어 드려요.'),
        'clarify': '어떤 걸 찾아 드릴까요? 행사 진행 상황, 승인 대기, 할 일, 동아리 자료라면 바로 찾아 드릴 수 있어요.',
    }.get(result.intent, '이 질문은 아직 제가 답하기 어려워요. 행사 진행 상황, 승인 대기, 할 일, 동아리 자료라면 바로 찾아 드릴 수 있어요.')
    return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply,
                                         suggestions=await _starters(session, club_id)))
