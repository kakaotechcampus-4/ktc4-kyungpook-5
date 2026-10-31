"""토리 단일 요청: 데이터 조회와 화면 안내만 제공한다."""
from datetime import date
from typing import Literal
from pydantic import Field, field_validator
from app.schemas.common import CamelModel
from app.schemas.records import RecordSearchData
from app.schemas.reminders import ConfirmedTaskOut


class ToriMessageIn(CamelModel):
    message: str = Field(min_length=1, max_length=4000)

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


class ToriMessageOut(CamelModel):
    intent: Literal['record_search', 'task_list', 'event_planning', 'meeting', 'clarify', 'unsupported']
    reply: str
    records: RecordSearchData | None = None
    record_total_count: int | None = None
    tasks: ToriTasks | None = None
    navigation: Literal['/planning', '/meetings'] | None = None
