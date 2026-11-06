"""토리 단일 요청의 소개·조회·화면 안내 계약."""
from datetime import date
from typing import Annotated, Literal
from pydantic import Field, field_validator
from app.schemas.common import CamelModel
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
                    'self_intro']
    reply: str
    records: RecordSearchData | None = None
    record_answer: ToriRecordAnswer | None = None
    clarification: ToriClarification | None = None
    record_total_count: int | None = None
    tasks: ToriTasks | None = None
    navigation: Literal['/planning', '/meetings'] | None = None
