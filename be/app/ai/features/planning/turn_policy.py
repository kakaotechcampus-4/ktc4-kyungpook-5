"""초안 생성 가능 여부를 값과 미해결 상태로 판단한다. 모델·DB 호출은 없다."""

from typing import Literal

from pydantic import model_validator

from ...contracts import ContractModel
from .schemas import PlanningConditions

READINESS_POLICY_VERSION = "planning-readiness-v1"
ReadinessReason = Literal["MISSING_EVENT_TYPE", "CONDITION_CONFLICT", "PENDING_MODIFICATION"]


class GenerationReadiness(ContractModel):
    ready_to_generate: bool
    reasons: tuple[ReadinessReason, ...]
    policy_version: Literal["planning-readiness-v1"] = READINESS_POLICY_VERSION

    @model_validator(mode="after")
    def _consistent(self):
        if self.ready_to_generate != (not self.reasons) or len(set(self.reasons)) != len(self.reasons):
            raise ValueError("생성 가능 여부와 보류 이유가 일치해야 합니다")
        return self


def assess_generation_readiness(
    conditions: PlanningConditions, *, has_pending_modification: bool = False,
    has_condition_conflict: bool = False,
) -> GenerationReadiness:
    """유형이 있고 미해결 수정·충돌이 없으면 초안을 허용한다. 행사 시작 판정과 다르다."""
    reasons: list[ReadinessReason] = []
    if conditions.event_type is None:
        reasons.append("MISSING_EVENT_TYPE")
    if has_condition_conflict:
        reasons.append("CONDITION_CONFLICT")
    if has_pending_modification:
        reasons.append("PENDING_MODIFICATION")
    return GenerationReadiness(ready_to_generate=not reasons, reasons=tuple(reasons))
