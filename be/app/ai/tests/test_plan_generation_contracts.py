"""권유의 의미 있는 기준과 채팅/버튼 입력의 경계를 고정한다."""

import pytest
from pydantic import ValidationError

from app.ai.features.planning.agent.state import ConditionMeta, PlanningDraft
from app.ai.features.planning.generation.catalog import CATALOG
from app.ai.features.planning.generation.offers import (
    UpdateGenerationOfferInput, same_basis, update_generation_offer,
)
from app.ai.features.planning.generation.schemas import (
    ButtonGenerationTrigger, ChatGenerationTrigger, PlanGenerationInput, PlanningGenerationState,
)
from app.ai.features.planning.schemas import MessageEvidence, PlanningConditions, PlanningMessage


def draft():
    return PlanningDraft(conditions=PlanningConditions(event_type="MT", headcount=50, fee_per_person=25000))


def message(text="날짜는 나중에", id="u1"):
    return PlanningMessage(id=id, role="user", text=text)


def test_button_trigger_has_no_chat_evidence_and_both_share_generation_input():
    for trigger in (ButtonGenerationTrigger(request_id="click-1"),
                    ChatGenerationTrigger(request_id="u1", quote="만들어줘")):
        req = PlanGenerationInput(basis_draft=draft(), trigger=trigger, reference_date="2026-10-24")
        assert PlanGenerationInput.model_validate_json(req.model_dump_json()) == req
    with pytest.raises(ValidationError):
        ButtonGenerationTrigger(request_id="click-1", quote="가짜 채팅")
    with pytest.raises(ValidationError):
        ChatGenerationTrigger(request_id="u1")


def test_same_basis_ignores_message_id_but_keeps_tentative_status_and_deferral():
    def variant(id, status="tentative", topics=()):
        return PlanningDraft(conditions=draft().conditions, deferred_topics=topics, condition_meta={
            "headcount": ConditionMeta(status=status, evidence=MessageEvidence(message_id=id, quote="50명"))})
    assert same_basis(variant("u1"), variant("u2"))
    assert not same_basis(variant("u1"), variant("u2", "specified"))
    assert not same_basis(variant("u1"), variant("u2", topics=("dates",)))


def test_offer_snapshots_draft_and_defer_prevents_same_basis_reoffer():
    before=draft()
    state=PlanningGenerationState()
    args=UpdateGenerationOfferInput(action="offer", reason="날짜 없이 준비 순서를 만들 수 있어요")
    first=update_generation_offer(before,state,args,current_message=message())
    assert first.status=="applied" and first.offer.basis_draft==before
    assert first.offer.basis_draft is not before
    state=PlanningGenerationState(offer=first.offer)
    assert update_generation_offer(before,state,args,current_message=message()).status=="unchanged"
    deferred=update_generation_offer(before,state,UpdateGenerationOfferInput(action="defer",reason="더 의논하기",
        evidence=MessageEvidence(message_id="u1",quote="아직 만들지 말자")),current_message=message("아직 만들지 말자"))
    state=PlanningGenerationState(offer=deferred.offer)
    assert deferred.offer.status=="deferred"
    assert update_generation_offer(before,state,args,current_message=message()).status=="rejected"
    changed=PlanningDraft(conditions=PlanningConditions(event_type="MT",headcount=40))
    assert update_generation_offer(changed,state,args,current_message=message()).status=="applied"


def test_offer_rejects_missing_type_unresolved_change_and_wrong_defer_evidence():
    args=UpdateGenerationOfferInput(action="offer",reason="만들까요")
    assert update_generation_offer(PlanningDraft(),PlanningGenerationState(),args,current_message=message()).status=="rejected"
    assert update_generation_offer(draft(),PlanningGenerationState(condition_change_pending=True),args,
                                   current_message=message()).status=="rejected"
    bad=UpdateGenerationOfferInput(action="defer",reason="미루기",evidence=MessageEvidence(message_id="old",quote="나중에"))
    assert update_generation_offer(draft(),PlanningGenerationState(),bad,current_message=message()).status=="rejected"
    with pytest.raises(ValidationError): UpdateGenerationOfferInput(action="defer",reason="미루기")


def test_catalog_is_13_planning_steps_without_cancellation_or_precreated_confirmation():
    assert len(CATALOG)==len({x.code for x in CATALOG})==13
    assert all(x.phase!="CANCELLATION" and "CONFIRMATION" not in x.actions for x in CATALOG)
