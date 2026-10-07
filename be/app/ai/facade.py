"""BE가 app.ai를 통해 호출할 AI 기능의 구현 위치.

함수와 입력·출력은 BE와 계약 합의 후 정의하고 __init__.py에서 재공개한다.
내부 HTTP 라우터를 만들지 않으며 기능 연결은 workflow에 위임한다.
"""

from .contracts import IndexRecordRequest, IndexRecordResult
from .errors import AIEmptyRecordError


async def index_record(request: IndexRecordRequest) -> IndexRecordResult:
    """기록을 청크로 나누고 임베딩한다.

    BE는 결과에 기록 메타데이터를 붙여 저장하고 parseStatus를 INDEXED로 바꾼다.
    읽을 블록이 없으면 AIEmptyRecordError를 올린다.
    """
    if not request.blocks:
        raise AIEmptyRecordError("색인할 내용이 없는 기록입니다")

    # 가짜 청크를 돌려주면 BE가 저장하고 INDEXED로 현재 막아둠
    raise NotImplementedError("index_record는 #71에서 구현한다")
