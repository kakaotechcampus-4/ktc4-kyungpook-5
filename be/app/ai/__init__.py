"""BE 내부 AI 모듈의 단일 공개 진입점.

공개 기능은 facade, 데이터는 contracts, 주입 계약은 ports, 오류는 errors에 정의한 뒤
여기서 명시적으로 재공개한다. BE는 여기 있는 이름만 사용한다.
enum은 재공개하지 않는다. `app.core.enums`에서 가져온다.
"""


from .contracts import (
    IndexedChunk,
    IndexRecordRequest,
    IndexRecordResult,
    RecordBlock,
    RecordSource,
    SourceLocation,
)
from .errors import (
    PlanningStateError,
    AIConfigError,
    AIEmptyRecordError,
    AIError,
    AIInvalidResponseError,
    AIOutputLimitError,
    AIRetryableError,
    AITimeoutError,
)
from .facade import index_record, judge_utterance
from .features.meeting.context import MEETING_CONTEXT_UTTERANCES
from .features.meeting.schemas import (
    JudgeTrace,
    JudgeUtteranceRequest,
    JudgeUtteranceResult,
    MeetingEvent,
    MeetingProgressPort,
    MeetingStage,
    MeetingUtterance,
    ToolCall,
)
from .llm import EMBEDDING_DIMENSIONS
from .ports import ChunkSearchQuery, RecordSearchPort, RetrievedChunk

__all__ = (
    # 기록 색인
    "index_record",
    "IndexRecordRequest",
    "IndexRecordResult",
    "IndexedChunk",
    "RecordBlock",
    "SourceLocation",
    # 회의 발화 처리. #113에서 BE와 합의하기 전의 초안이라 바뀔 수 있다 (docs/contracts.md)
    "judge_utterance",
    "JudgeUtteranceRequest",
    "JudgeUtteranceResult",
    "MeetingUtterance",
    "MeetingEvent",
    "JudgeTrace",
    "ToolCall",
    "MeetingProgressPort",
    "MeetingStage",
    # BE가 judge_utterance에 실어 보낼 앞 발화 수
    "MEETING_CONTEXT_UTTERANCES",
    # 기록 검색 port (BE가 구현)
    "RecordSearchPort",
    "ChunkSearchQuery",
    "RetrievedChunk",
    "RecordSource",
    # 청크 벡터 컬럼 차원
    "EMBEDDING_DIMENSIONS",
    # 오류. BE가 타입으로 재시도 안내·FAILED 처리를 정한다 (docs/errors.md)
    "AIError",
    "AIConfigError",
    "AIEmptyRecordError",
    "AIRetryableError",
    "AITimeoutError",
    "AIInvalidResponseError",
    "AIOutputLimitError",
)

# P1 공개 데이터 계약 초안 (#180). 실행 함수는 아래 #181에서 연결한다.
from .contracts import (
    PlanningChatRequest, PlanningPreviewRequest, PlanningUserMessage,
    PlanningResumeState, PlanningPublicResult, PlanningView,
    PlanningGenerationReadiness, PlanningDraft, PlanningConditions, PlanningHistoryUsage,
)
from .features.planning.state_codec import parse_resume_state

__all__ += (
    "PlanningChatRequest", "PlanningPreviewRequest", "PlanningUserMessage",
    "PlanningResumeState", "PlanningPublicResult", "PlanningView",
    "PlanningGenerationReadiness", "PlanningStateError", "PlanningDraft",
    "PlanningConditions", "parse_resume_state", "PlanningHistoryUsage",
)

# P1 실행 계약 초안 (#181). 제품 저장/HTTP는 BE가 연결한다.
from .facade import chat_planning, generate_planning_preview
__all__ += ('chat_planning', 'generate_planning_preview')

# 회의 일정·할 일 후보 (자료 조회와 독립)
from .facade import extract_task_suggestions
from .features.meeting.task_extraction import TaskExtractionRequest, TaskExtractionResult, TaskSuggestion
__all__ += ("extract_task_suggestions", "TaskExtractionRequest", "TaskExtractionResult", "TaskSuggestion")
