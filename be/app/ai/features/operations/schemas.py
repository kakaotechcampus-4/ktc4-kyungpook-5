"""운영 상황 확인과 후속 제안의 공개 데이터 형식."""
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from app.core.enums import EventType
from ...contracts import CalendarDate, ContractModel, Headcount


SituationText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
OptionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
SummaryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
SuggestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
TitleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
LocationText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class OperationalEventContext(ContractModel):
    title: TitleText
    event_type: EventType | None = None
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    location: LocationText | None = None
    expected_headcount: Headcount | None = None

    @model_validator(mode='after')
    def valid_dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError('종료일은 시작일보다 빠를 수 없습니다')
        return self


class OperationalSituationRequest(ContractModel):
    event_context: OperationalEventContext
    situation: SituationText
    clarification_question: QuestionText | None = None
    clarification_options: tuple[OptionText, ...] = Field(default=(), max_length=3)
    answer: OptionText | None = None

    @model_validator(mode='after')
    def valid_follow_up(self) -> Self:
        if (self.answer is None) != (self.clarification_question is None):
            raise ValueError('후속 답변에는 이전 확인 질문이 함께 필요합니다')
        if self.clarification_options and self.clarification_question is None:
            raise ValueError('확인 질문 없이 선택지를 전달할 수 없습니다')
        return self


class OperationalSituationResult(ContractModel):
    status: Literal['clarification', 'suggestion']
    question: QuestionText | None = None
    options: tuple[OptionText, ...] = Field(default=(), max_length=3)
    summary: SummaryText | None = None
    suggestions: tuple[SuggestionText, ...] = Field(default=(), max_length=5)

    @model_validator(mode='after')
    def valid_status(self) -> Self:
        if self.status == 'clarification':
            if not self.question or self.summary is not None or self.suggestions:
                raise ValueError('확인에는 질문만 필요합니다')
            if len(self.options) != len(set(self.options)):
                raise ValueError('확인 선택지는 중복할 수 없습니다')
        elif self.question is not None or self.options or not self.summary or not self.suggestions:
            raise ValueError('제안에는 요약과 후속 제안이 필요합니다')
        return self
