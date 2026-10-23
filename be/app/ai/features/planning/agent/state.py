"""새 계획 Agent의 작업 노트. 대화 메시지와 그래프 실행 정보는 2단계에서 연결한다."""

from typing import Literal, Self

from pydantic import Field, model_validator

from ....contracts import ContractModel
from ..schemas import ConditionField, MessageEvidence, PlanningConditions


ConditionStatus = Literal["tentative", "specified"]
PlanningTopic = Literal[
    "title", "event_type", "headcount", "fee_per_person", "dates", "location", "budget_total",
]


def topic_for(field: ConditionField) -> PlanningTopic:
    """시작일·종료일은 함께 의논하는 날짜 주제로 취급한다."""
    return "dates" if field in {"start_date", "end_date"} else field


class ConditionMeta(ContractModel):
    """값을 얼마나 정해 두었는지와 근거. specified도 최종 승인은 아니다."""

    status: ConditionStatus
    evidence: MessageEvidence


class PlanningDraft(ContractModel):
    """조건 값·부가정보·보류를 함께 반환하는 초안. BE 저장 모델이 아니다.

    frozen은 내부 dict까지 잠그지 않는다. 처리기는 복사본으로 작업하고
    새 PlanningDraft를 검증해 반환하며, 입력의 condition_meta를 수정하지 않는다.
    """

    conditions: PlanningConditions = Field(default_factory=PlanningConditions)
    condition_meta: dict[ConditionField, ConditionMeta] = Field(default_factory=dict)
    deferred_topics: tuple[PlanningTopic, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if any(getattr(self.conditions, field) is None for field in self.condition_meta):
            raise ValueError("미정인 조건에는 잠정/명시 메타정보를 붙일 수 없습니다")
        if len(self.deferred_topics) != len(set(self.deferred_topics)):
            raise ValueError("보류 주제는 중복될 수 없습니다")
        return self
