"""실제 조건 추출 → 질문 선택 → 다음 답변을 잇는 작은 통합 점검. 합성 정답 초안."""

import asyncio
import json

from app.ai.config import get_settings
from app.ai.features.planning.nodes import extract_condition_changes, PROMPT_VERSION
from app.ai.features.planning.questions import PlanningQuestionState, select_next_question, QUESTION_POLICY_VERSION
from app.ai.features.planning.schemas import ConditionExtractionInput


async def main():
    get_settings().require_api()
    scenarios = [
        ("defer_people", {"headcount": 32}, ["인원을 좀 줄이자", "아직 모르겠어"], [("headcount",), ("event_type",)]),
        ("answer_people", {"headcount": 32, "event_type": "MT"}, ["인원을 좀 줄이자", "40명으로 하자"], [("headcount",), ("start_date", "end_date")]),
        ("defer_dates", {"event_type": "MT"}, ["일정은 다음 달쯤으로 하자", "일정은 나중에 정할게"], [("start_date", "end_date"), ("headcount",)]),
    ]
    rows = []
    for case_id, conditions, utterances, expected in scenarios:
        state = PlanningQuestionState(event_id=case_id)
        history = []
        for i, text in enumerate(utterances):
            current = {"id": f"u{i}", "role": "user", "text": text}
            request = ConditionExtractionInput.model_validate({
                "event_id": case_id, "request_id": f"{case_id}-{i}", "base_version": i,
                "conditions": conditions, "current_message": current, "context_messages": history,
                "reference_date": "2026-10-22", "timezone": "Asia/Seoul",
            })
            extraction = await extract_condition_changes(request)
            answer = select_next_question(extraction, state)
            fields = answer.question.fields if answer.question else ()
            rows.append({"case": case_id, "turn": i, "input": text, "pass": fields == expected[i],
                         "expected_fields": expected[i], "extraction": extraction.model_dump(mode="json"),
                         "question_result": answer.model_dump(mode="json")})
            history.append(current)
            if answer.question:
                history.append({"id": f"a{i}", "role": "assistant", "text": answer.question.text})
            state, conditions = answer.state, extraction.candidate_conditions.model_dump(mode="json")
    print(json.dumps({"model": get_settings().model, "prompt_version": PROMPT_VERSION,
                      "question_policy": QUESTION_POLICY_VERSION, "review_status": "AI-authored draft, human review pending",
                      "matched": sum(r["pass"] for r in rows), "count": len(rows), "results": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
