"""BE가 권한 확인 후 전달한 행사 스냅샷을 회의 답변으로 정리한다."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.core.enums import EventStatus
from ...contracts import CalendarDate, ContractModel, NonBlankStr


EventFactField = Literal['status', 'dates', 'location', 'expected_headcount', 'actual_headcount']
Count = Annotated[int, Field(strict=True, ge=0)]


class MeetingEventFact(ContractModel):
    event_id: NonBlankStr
    title: NonBlankStr = Field(max_length=100)
    status: EventStatus
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    location: NonBlankStr | None = Field(default=None, max_length=200)
    expected_headcount: Count | None = None
    actual_headcount: Count | None = None

    @model_validator(mode='after')
    def valid_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('종료일이 시작일보다 빠를 수 없습니다')
        return self


class MeetingEventFactsRequest(ContractModel):
    scope: Literal['current', 'recent', 'selected']
    fields: tuple[EventFactField, ...] = Field(min_length=1, max_length=5)
    events: tuple[MeetingEventFact, ...] = Field(max_length=20)
    complete: bool
    latest_verified: bool = False

    @model_validator(mode='after')
    def valid_scope(self) -> Self:
        if len(self.fields) != len(set(self.fields)):
            raise ValueError('질문 필드는 중복할 수 없습니다')
        if len({event.event_id for event in self.events}) != len(self.events):
            raise ValueError('행사 ID는 중복할 수 없습니다')
        if self.latest_verified and (self.scope != 'recent' or not self.complete):
            raise ValueError('최신성 확인은 완전한 최근 행사 조회에만 허용됩니다')
        return self


class MeetingEventFactsResult(ContractModel):
    status: Literal['answered', 'partial', 'not_found', 'unavailable']
    answer: NonBlankStr
    event_ids: tuple[NonBlankStr, ...] = ()


_LABELS = {
    EventStatus.PLANNING: '계획 중', EventStatus.ON_GOING: '진행 중',
    EventStatus.COMPLETE: '완료', EventStatus.CANCELLING: '취소 중',
    EventStatus.CANCELLED: '취소됨',
}


def answer_meeting_event_facts(request: MeetingEventFactsRequest) -> MeetingEventFactsResult:
    """확인된 스냅샷만 표시한다. 조회와 대상 선택은 BE가 맡는다."""
    if not request.events:
        if request.complete:
            return MeetingEventFactsResult(status='not_found', answer='조회한 범위에 행사가 없어요.')
        return MeetingEventFactsResult(status='unavailable', answer='행사 정보를 확인하지 못했어요.')

    missing = not request.complete
    lines = []
    for event in request.events:
        values = []
        for field in request.fields:
            if field == 'status':
                values.append(f'상태: {_LABELS[event.status]}')
            elif field == 'dates':
                start = event.start_date.isoformat() if event.start_date else '미확인'
                end = event.end_date.isoformat() if event.end_date else '미확인'
                values.append(f'시작일: {start}, 종료일: {end}')
                missing |= event.start_date is None or event.end_date is None
            elif field == 'location':
                values.append(f'장소: {event.location or "미확인"}')
                missing |= event.location is None
            else:
                count = getattr(event, field)
                label = '예상 인원' if field == 'expected_headcount' else '실제 참가 인원'
                values.append(f'{label}: {count}명' if count is not None else f'{label}: 미확인')
                missing |= count is None
        lines.append(f'{event.title}: ' + ' · '.join(values))
    if not request.complete:
        lines.append('조회 범위 전체는 확인하지 못했어요.')
    if request.scope == 'recent' and not request.latest_verified:
        lines.append('전체 행사 중 가장 최근인지 확인하지 못했어요.')
        missing = True
    return MeetingEventFactsResult(status='partial' if missing else 'answered',
                                   answer='\n'.join(lines),
                                   event_ids=tuple(event.event_id for event in request.events))
