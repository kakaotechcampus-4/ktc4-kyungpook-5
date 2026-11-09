"""자료함 파일명·파싱 본문과 AI 청크 검색을 문서 단위로 합친다."""
from collections.abc import Mapping

from sqlalchemy import column, exists, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.core.enums import RecordFileType, RecordParseStatus
from app.models.records import Record
from app.services.record_search_port import PostgresRecordSearch

SEMANTIC_LIMIT = 50
SEMANTIC_MIN_SCORE = 0.20
SEMANTIC_MAX_GAP = 0.05
LEXICAL_ANSWER_LIMIT = 20
LEXICAL_BLOCK_MAX_CHARS = 4000

# 자료함 화면의 AI 추천 거르기(테스트 브랜치). AI 검색은 가까운 순으로 기준 없이 가져오므로
# 화면에 보일 자료만 여기서 고른다. 공용 검색(retrieve)과 계획 대화·회의 경로는 바꾸지 않는다.
# 값은 text-embedding-3-small 기준 로컬 측정(2026-11-05, 큰나무 예시 10건)에서 잡은 시작값이다.
SEMANTIC_MIN_TOP_SCORE = 0.25  # 1등이 이보다 낮으면 관련 자료가 없다고 본다
SEMANTIC_SCORE_WINDOW = 0.10  # 1등보다 이만큼 넘게 낮은 자료는 뺀다
SEMANTIC_MAX_RECORDS = 5


def select_semantic_records(
    scores: Mapping[str, float],
    *,
    min_top: float = SEMANTIC_MIN_TOP_SCORE,
    window: float = SEMANTIC_SCORE_WINDOW,
    max_records: int = SEMANTIC_MAX_RECORDS,
) -> set[str]:
    """자료별 최고 AI 점수에서 화면에 AI 추천으로 보일 자료 id를 고른다."""
    if not scores:
        return set()
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    top = ranked[0][1]
    if top < min_top:
        return set()
    return {record_id for record_id, score in ranked[:max_records] if score >= top - window}


def _excerpt(text: str, query: str | None = None) -> str:
    if not query:
        return text[:300]
    index = text.casefold().find(query.casefold())
    start = max(0, index - 80)
    return text[start:start + 300]


async def search_records(session: AsyncSession, *, club_id: str, query: str,
                         page: int, size: int,
                         chunks_out: list[ai.RetrievedChunk] | None = None,
                         lexical_out: list[ai.RetrievedChunk] | None = None,
                         lexical_omitted: list[bool] | None = None,
                         filename_only_out: list[str] | None = None,
                         semantic_filter: bool = False) -> tuple[dict, int]:
    # blocks.text만 검색한다. 파일명과 내용 모두 LIKE 특수문자를 그대로 취급한다.
    blocks = func.jsonb_array_elements(Record.parse_result['blocks']).table_valued(
        column('value', JSONB)
    ).alias('block')
    content_match = exists(select(1).select_from(blocks).where(
        blocks.c.value['text'].astext.icontains(query, autoescape=True)
    ))
    filename_match = Record.file_name.icontains(query, autoescape=True)
    lexical = list((await session.scalars(select(Record).where(
        Record.club_id == club_id, filename_match | content_match
    ).order_by(Record.id))).all())
    # 회계에서 확정한 영수증 사진(IMAGE)은 색인하지 않는 자료다. 'AI 검색 준비 전' 수에서 뺀다.
    counts = dict((await session.execute(select(Record.parse_status, func.count())
        .where(Record.club_id == club_id, Record.file_type != RecordFileType.IMAGE)
        .group_by(Record.parse_status))).all())
    indexed_count = counts.get(RecordParseStatus.INDEXED, 0)
    unindexed_count = sum(counts.values()) - indexed_count
    # 외부 모델 요청 동안 트랜잭션 연결을 유지하지 않는다.
    await session.commit()
    semantic_status = 'AVAILABLE' if indexed_count else 'NO_INDEXED_RECORDS'
    semantic = ()
    assessment_chunks = ()
    answer = None
    if indexed_count:
        try:
            semantic = await ai.search_related_records(
                ai.RecordDiscoveryRequest(club_id=club_id, query=query, limit=SEMANTIC_LIMIT),
                records=PostgresRecordSearch(club_id),
            )
            assessment_chunks = semantic[:12]
            if semantic:
                best_score = semantic[0].score
                semantic = tuple(
                    chunk for chunk in semantic
                    if chunk.score >= SEMANTIC_MIN_SCORE and best_score - chunk.score <= SEMANTIC_MAX_GAP
                )
            if semantic:
                try:
                    from app.ai.features.retrieval.nodes import assess_chunks
                    from app.ai.features.retrieval.schemas import RecordSearchRequest
                    from datetime import date
                    assessed = await assess_chunks(
                        RecordSearchRequest(club_id=club_id, query=query, today=date.today(), limit=SEMANTIC_LIMIT),
                        assessment_chunks,
                    )
                    if assessed.facts:
                        seen: set[str] = set()
                        facts = []
                        for fact in assessed.facts:
                            content = ' '.join(fact.content.split())
                            if content and content not in seen:
                                seen.add(content)
                                facts.append(content)
                        if facts:
                            answer = '\n'.join(f'• {fact}' for fact in facts[:5])
                except ai.AIError:
                    pass
        except ai.AIError:
            semantic_status = 'UNAVAILABLE'
    if not answer:
        answer = '질문에 답할 관련 자료를 찾지 못했습니다.'
    if chunks_out is not None:
        chunks_out.extend(semantic)
    if lexical_out is not None:
        omitted = False
        for record in lexical:
            if record.parse_status not in (RecordParseStatus.COMPLETED, RecordParseStatus.INDEXED):
                continue
            for block in (record.parse_result or {}).get('blocks', []):
                text = block.get('text', '')
                if not isinstance(text, str) or query.casefold() not in text.casefold():
                    continue
                location = block.get('location')
                label = location.get('label') if isinstance(location, dict) else None
                if not isinstance(label, str) or not label.strip() or len(text) > LEXICAL_BLOCK_MAX_CHARS:
                    omitted = True
                    continue
                if len(lexical_out) >= LEXICAL_ANSWER_LIMIT:
                    omitted = True
                    continue
                lexical_out.append(ai.RetrievedChunk(
                    text=text, source=ai.RecordSource(record_id=record.id,
                        file_name=record.file_name, location=ai.SourceLocation(label=label)),
                    category=record.category, event_id=record.event_id, score=0.0))
        if lexical_omitted is not None:
            lexical_omitted.append(omitted)
    semantic_by_record = {}
    for chunk in semantic:
        semantic_by_record.setdefault(chunk.source.record_id, chunk)
    if semantic_filter:
        # 자료함 화면 전용. 토리 대화는 기본값(False)으로 지금처럼 모두 받는다.
        kept = select_semantic_records(
            {record_id: chunk.score for record_id, chunk in semantic_by_record.items()}
        )
        semantic_by_record = {
            record_id: chunk for record_id, chunk in semantic_by_record.items() if record_id in kept
        }
    missing_ids = set(semantic_by_record) - {record.id for record in lexical}
    semantic_rows = []
    if missing_ids:
        semantic_rows = list((await session.scalars(select(Record).where(
            Record.club_id == club_id, Record.parse_status == RecordParseStatus.INDEXED,
            Record.id.in_(missing_ids)
        ))).all())
    items = []
    for record in lexical + semantic_rows:
        types = []
        excerpts = []
        if query.casefold() in record.file_name.casefold():
            types.append('FILENAME')
        for block in (record.parse_result or {}).get('blocks', []):
            text = block.get('text', '')
            if isinstance(text, str) and query.casefold() in text.casefold():
                if 'CONTENT' not in types:
                    types.append('CONTENT')
                if len(excerpts) < 3:
                    excerpts.append({'text': _excerpt(text, query), 'location': block.get('location')})
        match = semantic_by_record.get(record.id)
        if match is not None and record.parse_status == RecordParseStatus.INDEXED:
            types.append('SEMANTIC')
            excerpt = {'text': _excerpt(match.text), 'location': match.source.location.model_dump(mode='json')}
            if len(excerpts) < 3 and excerpt not in excerpts:
                excerpts.append(excerpt)
        if not types:
            continue
        if filename_only_out is not None and 'FILENAME' in types and 'CONTENT' not in types:
            filename_only_out.append(record.id)
        items.append({'record': record, 'match_types': types, 'excerpts': excerpts,
                      'semantic_score': match.score if match is not None and 'SEMANTIC' in types else None})
    # 의미 관련도를 먼저 보여주고, 같은 관련도 안에서 키워드 일치를 앞세운다.
    items.sort(key=lambda item: (-(item['semantic_score'] if item['semantic_score'] is not None else -2),
                                 0 if 'FILENAME' in item['match_types'] else 1 if 'CONTENT' in item['match_types'] else 2,
                                 item['record'].file_name.casefold(), item['record'].id))
    total = len(items)
    selected = items[(page - 1) * size:page * size]
    from app.schemas.records import RecordSearchItem
    return {'answer': answer, 'items': [RecordSearchItem.model_validate({
                **{field: getattr(item['record'], field) for field in RecordSearchItem.model_fields if hasattr(item['record'], field)},
                'match_types': item['match_types'], 'excerpts': item['excerpts'], 'semantic_score': item['semantic_score'],
            }) for item in selected],
            'semantic_status': semantic_status, 'indexed_count': indexed_count,
            'unindexed_count': unindexed_count, 'semantic_candidate_limit': SEMANTIC_LIMIT}, total
