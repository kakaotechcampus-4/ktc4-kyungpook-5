"""운영 상황 확인과 후속 제안, 운영 Action 본문 초안의 공개 데이터 형식."""
import re
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, computed_field, model_validator

from app.core.enums import ActionType, EventType, StepCode
from ...contracts import CalendarDate, ContractModel, Headcount, Won


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


# ── 운영 Action 본문 초안 (#333) ──────────────────────────────────────────
# 행사가 운영 중일 때 어떤 단계가 현재 단계가 되면, BE가 그 단계의 공지·발송 Action마다
# 이 입력을 만들어 draft_action_content()를 부른다. AI는 본문만 쓰고 저장·상태 변경은 BE가 한다.
# 날짜는 모두 BE가 한국 시간 날짜로 바꿔서 넘긴다. 시각을 주면 모델이 그대로 받아 써서
# 지어낸 마감 시각처럼 보이기 때문이다.

ClubNameText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
StepNameText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ActionTitleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
DraftText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]

# 본문에서 대괄호는 자리표시에만 쓴다. 예: "신청 방법: [신청 링크]" → "신청 링크"
_PLACEHOLDER = re.compile(r'\[([^\[\]\n]+)\]')


def draft_placeholders(content: str) -> tuple[str, ...]:
    """본문의 [ ] 자리표시를 나온 순서대로, 같은 글자는 한 번만 돌려준다."""
    found = (match.strip() for match in _PLACEHOLDER.findall(content))
    return tuple(dict.fromkeys(name for name in found if name))


class ActionDraftEvent(ContractModel):
    title: TitleText
    event_type: EventType | None = None
    # 운영을 시작한 행사에는 시작일이 항상 있다(start_event가 확인).
    start_date: CalendarDate
    end_date: CalendarDate | None = None
    location: LocationText | None = None
    # 예상 인원은 실제 참가 인원도 정원도 아니다.
    expected_headcount: Headcount | None = None
    fee_per_person: Won | None = None

    @model_validator(mode='after')
    def valid_dates(self) -> Self:
        if self.end_date and self.end_date < self.start_date:
            raise ValueError('종료일은 시작일보다 빠를 수 없습니다')
        return self


class ActionDraftStep(ContractModel):
    code: StepCode
    name: StepNameText
    starts_on: CalendarDate | None = None
    deadline: CalendarDate | None = None


class ActionDraftAction(ContractModel):
    # 글로 내보내는 일만 초안을 쓴다. 계약·송금·지출은 금액과 대상이 핵심이라 대상이 아니다.
    type: Literal[ActionType.NOTICE, ActionType.EXTERNAL_SEND]
    title: ActionTitleText
    due_date: CalendarDate | None = None
    amount: Won | None = None


class ActionDraftRequest(ContractModel):
    club_name: ClubNameText
    event: ActionDraftEvent
    step: ActionDraftStep
    action: ActionDraftAction
    today: CalendarDate


class ActionDraftResult(ContractModel):
    content: DraftText

    # 모델이 따로 적게 하면 본문과 글자가 어긋나므로, 본문에서 계산한 값만 쓴다.
    # 결과를 만들 때 넘기는 값이 아니라 content에서 읽는 값이다.
    @computed_field
    @property
    def unknowns(self) -> tuple[str, ...]:
        return draft_placeholders(self.content)
