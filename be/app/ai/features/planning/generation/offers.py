"""권유 상태는 코드로 남기고, 권유할 타이밍과 말투는 대화 Agent가 고른다."""

from typing import Literal, Self
from uuid import uuid4

from pydantic import model_validator

from ....contracts import ContractModel, NonBlankStr
from ..agent.state import PlanningDraft
from ..schemas import MessageEvidence, PlanningMessage
from .schemas import GenerationOffer, PlanningGenerationState


def same_basis(left: PlanningDraft, right: PlanningDraft) -> bool:
    """발화 ID 변화는 무시하되 잠정→명시·보류 변화는 계획 기준의 변화로 본다."""
    return (left.conditions == right.conditions
            and {k: v.status for k, v in left.condition_meta.items()} ==
                {k: v.status for k, v in right.condition_meta.items()}
            and set(left.deferred_topics) == set(right.deferred_topics))


def valid_evidence(evidence: MessageEvidence, message: PlanningMessage) -> bool:
    return (message.role == "user" and evidence.message_id == message.id
            and evidence.quote in message.text)


class UpdateGenerationOfferInput(ContractModel):
    action: Literal["offer", "defer"]
    reason: NonBlankStr
    evidence: MessageEvidence | None = None

    @model_validator(mode="after")
    def _defer_evidence(self) -> Self:
        if self.action == "defer" and self.evidence is None:
            raise ValueError("보류에는 이번 사용자 발화 근거가 필요합니다")
        return self


class OfferUpdateResult(ContractModel):
    status: Literal["applied", "unchanged", "rejected"]
    offer: GenerationOffer | None
    reason: NonBlankStr | None = None


def update_generation_offer(
    draft: PlanningDraft, state: PlanningGenerationState, arguments: UpdateGenerationOfferInput,
    *, current_message: PlanningMessage,
) -> OfferUpdateResult:
    def reject(reason: str) -> OfferUpdateResult:
        return OfferUpdateResult(status="rejected", offer=state.offer, reason=reason)

    if arguments.action == "defer":
        if not valid_evidence(arguments.evidence, current_message):
            return reject("보류에는 이번 사용자 발화의 실제 문구가 필요해요.")
    else:
        if draft.conditions.event_type is None or state.condition_change_pending:
            return reject("행사 유형이나 반영하지 못한 조건 변경을 먼저 확인해 주세요.")
        if state.offer and same_basis(state.offer.basis_draft, draft):
            if state.offer.status == "deferred":
                return reject("같은 조건의 생성 권유를 보류했어요. 대화를 이어가 주세요.")
            return OfferUpdateResult(status="unchanged", offer=state.offer)
        if state.preview and same_basis(state.preview.basis_draft, draft):
            return reject("현재 조건으로 만든 계획 초안이 이미 있어요.")

    # 제안 ID와 기준 조건은 모델 인자가 아니라 코드가 만든다.
    offer = GenerationOffer(id=str(uuid4()), status="deferred" if arguments.action == "defer" else "pending",
                            summary=arguments.reason, basis_draft=draft.model_copy(deep=True))
    return OfferUpdateResult(status="applied", offer=offer)
