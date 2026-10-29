"""자료함 파일명·파싱 본문과 AI 청크 검색을 문서 단위로 합친다."""
from sqlalchemy import column, exists, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app import ai
from app.core.enums import RecordParseStatus
from app.models.records import Record
from app.services.record_search_port import PostgresRecordSearch

SEMANTIC_LIMIT = 50


def _excerpt(text: str, query: str | None = None) -> str:
    if not query:
        return text[:300]
    index = text.casefold().find(query.casefold())
    start = max(0, index - 80)
    return text[start:start + 300]


async def search_records(session: AsyncSession, *, club_id: str, query: str,
                         page: int, size: int) -> tuple[dict, int]:
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
    ))).all())
    counts = dict((await session.execute(select(Record.parse_status, func.count())
        .where(Record.club_id == club_id).group_by(Record.parse_status))).all())
    indexed_count = counts.get(RecordParseStatus.INDEXED, 0)
    unindexed_count = sum(counts.values()) - indexed_count
    # 외부 모델 요청 동안 트랜잭션 연결을 유지하지 않는다.
    await session.commit()
    semantic_status = 'AVAILABLE' if indexed_count else 'NO_INDEXED_RECORDS'
    semantic = ()
    if indexed_count:
        try:
            semantic = await ai.search_related_records(
                ai.RecordDiscoveryRequest(club_id=club_id, query=query, limit=SEMANTIC_LIMIT),
                records=PostgresRecordSearch(club_id),
            )
        except ai.AIError:
            semantic_status = 'UNAVAILABLE'
    semantic_by_record = {}
    for chunk in semantic:
        semantic_by_record.setdefault(chunk.source.record_id, chunk)
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
        items.append({'record': record, 'match_types': types, 'excerpts': excerpts,
                      'semantic_score': match.score if match is not None and 'SEMANTIC' in types else None})
    # Exact filename/content matches first; stable tie breaks for the same snapshot.
    items.sort(key=lambda item: (0 if 'FILENAME' in item['match_types'] else 1 if 'CONTENT' in item['match_types'] else 2,
                                 -(item['semantic_score'] if item['semantic_score'] is not None else -2),
                                 item['record'].file_name.casefold(), item['record'].id))
    total = len(items)
    selected = items[(page - 1) * size:page * size]
    from app.schemas.records import RecordSearchItem
    return {'items': [RecordSearchItem.model_validate({
                **{field: getattr(item['record'], field) for field in RecordSearchItem.model_fields if hasattr(item['record'], field)},
                'match_types': item['match_types'], 'excerpts': item['excerpts'], 'semantic_score': item['semantic_score'],
            }) for item in selected],
            'semantic_status': semantic_status, 'indexed_count': indexed_count,
            'unindexed_count': unindexed_count, 'semantic_candidate_limit': SEMANTIC_LIMIT}, total
