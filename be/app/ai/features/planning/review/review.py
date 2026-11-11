"""사용자가 고친 행사 계획을 검토해 걱정되는 점을 0~4개로 돌려준다. 저장·확정은 하지 않는다."""
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ....contracts import PlanEditReviewRequest, PlanEditReviewResult
from ....errors import AIInvalidResponseError
from ....llm import ainvoke_structured

_PROMPT = (Path(__file__).parent / "prompts" / "review.md").read_text(encoding="utf-8")


async def review_plan_edit(request: PlanEditReviewRequest) -> PlanEditReviewResult:
    # 요청 JSON은 데이터이므로 지시문과 섞지 않고 별도 사용자 메시지로만 보낸다.
    messages = [SystemMessage(_PROMPT), HumanMessage(request.model_dump_json())]
    result = await ainvoke_structured(messages, PlanEditReviewResult)

    # 모델이 입력에 없는 단계를 지어내면 화면에 잘못된 안내가 나가므로 막는다.
    known = {s.code for s in request.included_steps} | {s.code for s in request.excluded_steps}
    if any(code not in known for item in result.items for code in item.step_codes):
        raise AIInvalidResponseError("검토 결과에 입력에 없는 단계 코드가 있습니다")
    return result
