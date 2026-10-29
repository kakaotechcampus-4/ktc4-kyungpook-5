"""BE가 app.ai를 통해 호출할 AI 기능의 구현 위치.

함수와 입력·출력은 BE와 계약 합의 후 정의하고 __init__.py에서 재공개한다.
회의 발화 처리(judge_utterance)는 BE가 #118에서 연결해 보도록 합의 전 초안을 먼저 공개한다.
내부 HTTP 라우터를 만들지 않으며 기능 연결은 workflow에 위임한다.
"""

from .contracts import IndexRecordRequest, IndexRecordResult
from .features.meeting.lookup import RecordsLookup
from .features.meeting.nodes import judge_utterance as judge_meeting_utterance
from .features.meeting.schemas import (
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingProgressPort,
)
from .features.retrieval.indexing import index_record_chunks
from .ports import RecordSearchPort
from .contracts import PlanningChatRequest, PlanningPreviewRequest, PlanningPublicResult


async def index_record(request: IndexRecordRequest) -> IndexRecordResult:
    """기록을 청크로 나누고 임베딩한다.

    BE는 결과에 기록 메타데이터를 붙여 저장하고 parseStatus를 INDEXED로 바꾼다.
    읽을 블록이 없으면 AIEmptyRecordError, 임베딩 호출이 실패하면 AI 오류 타입을 올린다.
    """
    return await index_record_chunks(request)


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    records: RecordSearchPort,
    progress: MeetingProgressPort | None = None,
) -> JudgeUtteranceResult:
    """회의 발화 하나를 판단하고, 기록 조회가 필요하면 기록을 찾아 출처가 붙은 답을 만든다.

    계약은 docs/contracts.md "회의 발화 처리 초안"이며 #113에서 BE와 합의하기 전이다.
    BE는 동아리 범위로 청크를 찾는 `records`만 넘긴다. 검색과 답 작성을 잇는 일은 AI가 한다.
    관련 기록이 없으면 NOT_FOUND이고, 처리에 실패하면 `trace`를 담은 AI 오류 타입을 올린다.
    """
    return await judge_meeting_utterance(
        request, lookup=RecordsLookup(records), progress=progress
    )


async def chat_planning(request: "PlanningChatRequest", *,
                        records: RecordSearchPort | None = None) -> "PlanningPublicResult":
    """P1 한 턴. records가 없으면 검색 Tool은 제공하지 않는다. 저장/권한은 BE 책임.

    계약은 팀 협의 전 초안이며 docs/planning/p1-public-contract.md를 따른다.
    """
    from .features.planning.public_workflow import chat
    return await chat(request, records=records)


async def generate_planning_preview(request: "PlanningPreviewRequest") -> "PlanningPublicResult":
    """P1 버튼 생성. 메시지를 추가하지 않고 기존 검색 근거와 조건으로 초안을 만든다."""
    from .features.planning.public_workflow import generate_preview
    return await generate_preview(request)


async def extract_task_suggestions(request: "TaskExtractionRequest") -> "TaskExtractionResult":
    """회의 발화에서 확인할 후보를 제안한다. 저장과 예약은 BE가 맡는다."""
    from .features.meeting.task_extraction import extract_task_suggestions as extract
    return await extract(request)
