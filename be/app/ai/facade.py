"""BE가 app.ai를 통해 호출할 AI 기능의 구현 위치.

함수와 입력·출력은 BE와 계약 합의 후 정의하고 __init__.py에서 재공개한다.
내부 HTTP 라우터를 만들지 않으며 기능 연결은 workflow에 위임한다.
"""

from .contracts import IndexRecordRequest, IndexRecordResult
from .features.retrieval.indexing import index_record_chunks


async def index_record(request: IndexRecordRequest) -> IndexRecordResult:
    """기록을 청크로 나누고 임베딩한다.

    BE는 결과에 기록 메타데이터를 붙여 저장하고 parseStatus를 INDEXED로 바꾼다.
    읽을 블록이 없으면 AIEmptyRecordError, 임베딩 호출이 실패하면 AI 오류 타입을 올린다.
    """
    return await index_record_chunks(request)
