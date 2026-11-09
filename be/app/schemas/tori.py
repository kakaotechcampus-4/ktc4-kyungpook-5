"""토리 단일 요청의 소개·조회·화면 안내 계약."""
from datetime import date
from typing import Annotated, Literal
from pydantic import Field, field_validator
from app.schemas.common import CamelModel
from app.schemas.events import EventOut
from app.schemas.records import RecordSearchData, RecordSearchLocation
from app.schemas.reminders import ConfirmedTaskOut


class ToriClarificationContext(CamelModel):
    original_question: str = Field(min_length=1, max_length=4000)
    question: str | None = Field(default=None, min_length=1, max_length=500)
    options: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=3)

    @field_validator('original_question')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('원래 질문을 입력해 주세요.')
        return value.strip()

    @field_validator('question')
    @classmethod
    def valid_question(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError('확인 질문을 입력해 주세요.')
        return value.strip() if value is not None else None

    @field_validator('options')
    @classmethod
    def valid_options(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('빈 선택지는 허용되지 않습니다.')
        return [value.strip() for value in values]


class ToriMessageIn(CamelModel):
    message: str = Field(min_length=1, max_length=4000)
    clarification_context: ToriClarificationContext | None = None

    @field_validator('message')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('메시지를 입력해 주세요.')
        return value.strip()


class ToriTasks(CamelModel):
    items: list[ConfirmedTaskOut]
    has_more: bool
    scope: Literal['self', 'all']
    kind: Literal['task', 'schedule', 'all']
    date_from: date | None = None
    date_to: date | None = None
    timezone: Literal['Asia/Seoul'] = 'Asia/Seoul'


class ToriRecordSource(CamelModel):
    record_id: str
    file_name: str
    location: RecordSearchLocation


class ToriRecordFact(CamelModel):
    text: str = Field(min_length=1)
    sources: list[ToriRecordSource] = Field(min_length=1)


class ToriRecordConflict(CamelModel):
    description: str = Field(min_length=1)
    values: list[ToriRecordFact] = Field(min_length=2)


class ToriRecordAnswer(CamelModel):
    status: Literal['answered', 'partial', 'insufficient', 'failed']
    facts: list[ToriRecordFact] = Field(default_factory=list)
    conflicts: list[ToriRecordConflict] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
    semantic_status: Literal['AVAILABLE', 'UNAVAILABLE', 'NO_INDEXED_RECORDS']
    unindexed_count: int = Field(ge=0)
    searched_chunk_count: int = Field(ge=0)
    candidate_limit: int = Field(ge=1)
    candidate_limit_reached: bool
    lexical_chunk_count: int = Field(ge=0)
    lexical_omitted: bool
    filename_only_unanalyzed_count: int = Field(ge=0)


class ToriClarification(CamelModel):
    original_question: str = Field(min_length=1, max_length=4000)
    question: str = Field(min_length=1, max_length=500)
    options: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=3)


class ToriMessageOut(CamelModel):
    intent: Literal['record_search', 'task_list', 'event_list', 'event_planning', 'meeting', 'clarify', 'unsupported',
                    'self_intro', 'briefing', 'approval_list', 'event_status', 'meeting_tasks']
    reply: str
    records: RecordSearchData | None = None
    record_answer: ToriRecordAnswer | None = None
    clarification: ToriClarification | None = None
    record_total_count: int | None = None
    tasks: ToriTasks | None = None
    navigation: Literal['/planning', '/meetings', '/records', '/accounting'] | None = None
    # 답 아래에 붙는 카드. 답 종류마다 하나씩이고, 카드가 없는 답은 null이다.
    card: 'ToriCard | None' = None
    # 이 답 다음에 이어서 물어볼 만한 말. 행사·회의를 되물을 때는 후보마다 하나씩이라 최대 5개다.
    suggestions: list[str] = Field(default_factory=list, max_length=5)


class ToriBriefingItem(CamelModel):
    """브리핑 「오늘 확인할 일」 한 줄. 화면 이동 주소는 FE가 event_id·task_id·meeting_id로 만든다."""

    id: str
    kind: Literal['deadline', 'approval', 'task']
    title: str
    # 어느 행사나 회의에서 온 일인지. "2026 봄 MT | 입금 확인 단계"처럼 화면에 그대로 쓴다.
    source: str
    # 한국 날짜. 승인 대기·할 일은 기한이 없으면 null이다.
    due_date: date | None = None
    # 같은 행사의 승인 대기가 더 있으면 그 수("외 n건").
    more_count: int = Field(default=0, ge=0)
    event_id: str | None = None
    task_id: str | None = None
    meeting_id: str | None = None
    # 이 줄을 토리에게 이어 물을 때 보낼 말. 없으면 「토리에게 묻기」를 띄우지 않는다.
    ask: str | None = None


class ToriBriefingOut(CamelModel):
    """메인 탭 첫 화면. items는 급한 순서이고, events는 진행 중 → 계획 중 순서다."""

    items: list[ToriBriefingItem]
    events: list[EventOut]


class ToriEventsCard(CamelModel):
    """행사 목록 답의 카드. total은 조건에 맞는 전체 수이고 events는 앞에서부터 최대 20건이다."""

    type: Literal['events'] = 'events'
    events: list[EventOut]
    total: int = Field(ge=0)


class ToriBriefingCard(CamelModel):
    """「확인할 일 전부 보여줘」의 카드. 브리핑 API의 items와 같은 줄을 전부 담는다."""

    type: Literal['briefing'] = 'briefing'
    items: list[ToriBriefingItem]


class ToriApprovalAction(CamelModel):
    id: str
    title: str
    step_name: str | None = None
    due_date: date | None = None


class ToriApprovalGroup(CamelModel):
    event_id: str
    event_title: str
    actions: list[ToriApprovalAction]


class ToriApprovalsCard(CamelModel):
    """승인 대기 카드. 운영 중 행사만, 행사별로 묶는다. 승인은 행사 상세에서 한다."""

    type: Literal['approvals'] = 'approvals'
    groups: list[ToriApprovalGroup]


class ToriStatusStep(CamelModel):
    name: str
    due_date: date | None = None


class ToriEventStatusCard(CamelModel):
    """행사 현황 카드. 운영 중이 아니면 current_step이 null이고 next_steps가 비어 있다."""

    type: Literal['event_status'] = 'event_status'
    event: EventOut
    current_step: ToriStatusStep | None = None
    next_steps: list[ToriStatusStep]
    # 승인 대기 행동 제목. 앞에서 최대 5개이고 전체 수는 approval_count다.
    approvals: list[str]
    approval_count: int = Field(ge=0)
    # 예산은 행사에 정한 총액(정하지 않았으면 null), 지출은 장부에서 이 행사로 적힌 금액의 합이다.
    budget: int | None = None
    spent: int


class ToriMeetingTask(CamelModel):
    id: str
    title: str
    kind: Literal['TASK', 'SCHEDULE']
    assignee_name: str | None = None
    # 할 일은 마감일, 일정은 날짜(한국 날짜).
    due_date: date | None = None


class ToriTasksCard(CamelModel):
    """회의에서 확정한 할 일·일정 카드."""

    type: Literal['tasks'] = 'tasks'
    title: str
    meeting_id: str
    tasks: list[ToriMeetingTask]
    has_more: bool


class ToriHandoffCard(CamelModel):
    """행사 계획 요청을 계획 화면으로 넘기는 카드. 조건은 계획 화면이 이 말에서 다시 뽑는다."""

    type: Literal['handoff'] = 'handoff'
    message: str


ToriCard = Annotated[
    ToriEventsCard | ToriBriefingCard | ToriApprovalsCard | ToriEventStatusCard | ToriTasksCard | ToriHandoffCard,
    Field(discriminator='type'),
]
ToriMessageOut.model_rebuild()
