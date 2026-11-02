"""인증된 소속의 토리 조회. 내용 변경이나 예약은 수행하지 않는다."""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
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
from app.schemas.tori import ToriMessageIn, ToriMessageOut, ToriRecordAnswer
from app.services import event_service, record_discovery_service

router = APIRouter(prefix='/api/v1/clubs/{club_id}/tori', tags=['tori'])
TZ = ZoneInfo('Asia/Seoul')


@router.post('/messages', response_model=Envelope[ToriMessageOut])
async def message(club_id: str, body: ToriMessageIn,
                  _member: Member = Depends(require_member),
                  account: Account = Depends(get_current_account),
                  session: AsyncSession = Depends(get_session)) -> Envelope[ToriMessageOut]:
    # 권한 확인 뒤 모델 호출 중 DB 연결을 점유하지 않는다.
    await session.commit()
    try:
        result = await ai.classify_tori_intent(ai.ToriIntentRequest(
            message=body.message, reference_date=datetime.now(TZ).date(), timezone='Asia/Seoul'))
    except ai.AIConfigError as error:
        raise AIMisconfigured() from error
    except ai.AIError as error:
        raise AIUnavailable() from error
    # 외부 호출 중 권한이 바뀔 수 있어 조회 전에 다시 검증한다.
    from app.core.deps import ensure_member
    await ensure_member(session, club_id=club_id, account=account)
    if result.intent == 'record_search':
        if not result.query or len(result.query) > 200:
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
        if records['semantic_status'] == 'UNAVAILABLE' and not chunks:
            answer = ToriRecordAnswer(status='failed', **answer_info)
        elif not chunks:
            answer = ToriRecordAnswer(status='insufficient', **answer_info)
        else:
            await session.commit()
            try:
                generated = await ai.answer_tori_records(ai.ToriRecordAnswerRequest(
                    question=body.message, today=datetime.now(TZ).date(), chunks=tuple(chunks)))
            except ai.AIError:
                answer = ToriRecordAnswer(status='failed', **answer_info)
            else:
                allowed = {chunk.source for chunk in chunks}
                facts = [*generated.facts, *(value for conflict in generated.conflicts for value in conflict.values)]
                def fact_out(fact):
                    return {'text': fact.content, 'sources': [source.model_dump() for source in fact.sources]}
                if any(source not in allowed for fact in facts for source in fact.sources):
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
            elif lexical:
                current_blocks = {
                    (record.id, record.file_name, block.get('location', {}).get('label'), block.get('text'))
                    for record in rows for block in (record.parse_result or {}).get('blocks', [])
                    if isinstance(block, dict) and isinstance(block.get('location'), dict)
                }
                if any((chunk.source.record_id, chunk.source.file_name,
                        chunk.source.location.label, chunk.text) not in current_blocks for chunk in lexical):
                    answer = ToriRecordAnswer(status='failed', **answer_info)
        item_ids = {item.id for item in records['items']}
        if item_ids:
            current_items = set((await session.scalars(select(Record.id).where(
                Record.id.in_(item_ids), Record.club_id == club_id))).all())
            records['items'] = [item for item in records['items'] if item.id in current_items]
        reply = {'answered': '자료에서 확인한 내용이에요.', 'partial': '자료에서 일부 내용을 확인했어요.',
                 'insufficient': '검색한 자료에서 답의 근거를 충분히 찾지 못했어요.',
                 'failed': '자료 답변을 만들지 못했어요. 검색 결과를 확인해 주세요.'}[answer.status]
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
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='요청하신 범위의 확정된 일정과 할 일을 보여드릴게요. 회의나 행사별 구분은 적용되지 않아요.', tasks=tasks))
    if result.intent == 'event_list':
        status = EventStatus(result.event_status) if result.event_status else None
        events, total = await event_service.list_events(session, club_id=club_id, status=status, page=1, size=20)
        labels = {'PLANNING': '계획 중', 'ON_GOING': '진행 중', 'COMPLETE': '완료',
                  'CANCELLING': '취소 중', 'CANCELLED': '취소됨'}
        label = labels[status.value] if status else '전체'
        if not events:
            reply = f'{label} 행사가 없어요.'
        else:
            lines = [f'{label} 행사 {total}건이에요.']
            for event in events:
                day = event['start_date'].isoformat() if event['start_date'] else '날짜 미정'
                lines.append(f"• {event['title']} ({labels[event['status'].value]} · {day})")
            if total > len(events):
                lines.append(f'처음 {len(events)}건을 보여드렸어요. 전체 목록은 행사 화면에서 확인해 주세요.')
            reply = '\n'.join(lines)
        return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply))
    if result.intent == 'event_planning':
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='행사 계획 화면으로 이동할 수 있어요.', navigation='/planning'))
    if result.intent == 'meeting':
        return Envelope(data=ToriMessageOut(intent=result.intent, reply='회의 화면으로 이동할 수 있어요.', navigation='/meetings'))
    reply = '어떤 자료나 일정, 할 일을 찾을지 조금 더 알려 주세요.' if result.intent == 'clarify' else '아직 이 요청은 처리할 수 없어요. 자료 검색이나 확정된 일정 조회를 요청해 주세요.'
    return Envelope(data=ToriMessageOut(intent=result.intent, reply=reply))
