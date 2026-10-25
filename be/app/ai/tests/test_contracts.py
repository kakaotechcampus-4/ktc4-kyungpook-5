"""planning 계약이 잘못된 값을 경계에서 막는지 검증한다.

빈 계획·빈 답변을 정상 결과로 돌려주지 않기 위한 불변식이다(AI-COMMON-02).
같은 프로세스 안의 호출이라 여기서 막지 못하면 그대로 저장되고 화면까지 간다.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.ai.contracts import (
    PlanDraft,
    PlannedStep,
)
from app.ai import PlanningDraft, PlanningGenerationReadiness, PlanningUserMessage, PlanningView
from app.core.enums import StepActor, StepPhase

STEP = PlannedStep(
    phase=StepPhase.PREPARATION,
    name="장소 후보 조사",
    actor=StepActor.MANUAL,
    starts_at=datetime(2026, 3, 1, tzinfo=UTC),
)


def _result(reply: str) -> PlanningView:
    return PlanningView(reply=reply, draft=PlanningDraft(),
        generation_readiness=PlanningGenerationReadiness(can_generate=False, reasons=('event_type_missing',)))


def test_이번_발화는_사용자_메시지_타입으로_받는다():
    assert PlanningUserMessage(id="u1", content="50명으로 잡자").content == "50명으로 잡자"
    with pytest.raises(ValidationError):
        PlanningUserMessage(id="u1", content="50명으로 잡자", role="assistant")


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_빈_사용자_발화는_거부한다(content):
    with pytest.raises(ValidationError):
        PlanningUserMessage(id="u1", content=content)


def test_답변에_내용이_있어야_한다():
    assert _result("정리했습니다.").reply == "정리했습니다."


@pytest.mark.parametrize("reply", ["", "   ", "\n\t"])
def test_비어_있거나_공백뿐인_답변은_거부한다(reply: str):
    """그대로 저장되면 빈 말풍선이 남아 실패가 성공처럼 보인다."""
    with pytest.raises(ValidationError) as error:
        _result(reply)

    assert "reply" in str(error.value)


def test_답변의_공백을_임의로_다듬지_않는다():
    """판정만 하고 값은 그대로 둔다. 계약이 내용을 손대지 않는다."""
    assert _result("  정리했습니다.\n").reply == "  정리했습니다.\n"


def test_단계가_하나는_있어야_계획안이_된다():
    assert PlanDraft(steps=(STEP,)).steps == (STEP,)


def test_단계가_없는_계획안은_거부한다():
    """운영 시작에는 시작일과 단계 하나가 필요하다(AI-PLAN-09)."""
    with pytest.raises(ValidationError):
        PlanDraft(steps=())


def test_계약_객체는_만든_뒤_바꿀_수_없다():
    """BE가 받은 결과를 고쳐 쓰면 AI가 무엇을 제안했는지 알 수 없게 된다."""
    result = _result("정리했습니다.")

    with pytest.raises(ValidationError):
        result.reply = "다른 답변"


def test_계약에_없는_필드는_거부한다():
    """이름이 바뀐 필드가 조용히 버려지지 않게 한다."""
    with pytest.raises(ValidationError):
        PlanningView(
            reply="정리했습니다.", draft=PlanningDraft(),
            generation_readiness=PlanningGenerationReadiness(can_generate=False, reasons=('event_type_missing',)),
            readyToGenerate=True,
        )
