# 행사계획 코드 따라가기

오랜만에 읽을 때는 [전체 설계](design.md)의 Node 흐름을 먼저 보고, 아래 단계별 입력 → 코드 → 결과를 따라간다. 현재 1단계는 Tool 처리기까지이며 그래프·LLM·UI는 아직 새 흐름에 연결되지 않았다.

## 1단계: 말을 반영할 수 있는 작업 노트와 처리기

사용자가 “날짜는 나중에, 대략 50명에 인당 25,000원으로 잡자”라고 말했다고 하자. 다음 단계의 LLM은 이 말을 읽고 `SET headcount=50`, `SET fee_per_person=25000`, `dates 보류` 요청을 만들게 된다. 이번에는 그 요청을 직접 만들어 처리기를 확인한다.

1. [agent/state.py](../../features/planning/agent/state.py)의 `PlanningDraft`: 행사 조건·잠정 여부·보류 주제를 보관한다.
2. [agent/tools.py](../../features/planning/agent/tools.py)의 `UpdateEventConditionsInput`: 바꿀 내용만 담는다. 전체 state를 덮어쓰는 요청이 아니다.
3. `update_event_conditions()`: 근거 확인 → 새 값 준비 → 최종 날짜 검증 → 메타정보·보류 갱신 → 결과 반환.

SET은 값을 채우고, CLEAR는 값을 미정으로 되돌린다. 아직 말하지 않은 조건은 그대로 둔다. 사용자와 어떤 대화를 할지는 다음 단계 agent Node가 선택한다.

## 직접 실행해보기

프로젝트 루트에서 `cd be` 후 아래 코드를 `.venv/bin/python`으로 실행한다. 실제 API를 호출하지 않는다. 현재 인원 32명에서 50명으로 바뀌는 예시다.

```python
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.agent.tools import UpdateEventConditionsInput, update_event_conditions
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage

before = PlanningDraft(conditions=PlanningConditions(event_type="MT", headcount=32))
message = PlanningMessage(
    id="user-1", role="user",
    text="날짜는 나중에, 대략 50명에 인당 25,000원으로 잡자",
)

def evidence(quote):
    return {"message_id": message.id, "quote": quote}

# 지금은 직접 작성한다. 2단계부터 이 인자를 LLM이 만들게 된다.
request = UpdateEventConditionsInput(
    changes=[
        {"op": "SET", "change": {"field": "headcount", "value": 50},
         "status": "tentative", "evidence": evidence("대략 50명")},
        {"op": "SET", "change": {"field": "fee_per_person", "value": 25000},
         "status": "tentative", "evidence": evidence("인당 25,000원")},
    ],
    defer_topics=[{"topic": "dates", "evidence": evidence("날짜는 나중에")}],
)
result = update_event_conditions(before, request, current_message=message)
print(result.status)
print(result.draft.conditions.headcount, result.draft.conditions.fee_per_person)
print(result.draft.condition_meta["headcount"].status)
print(result.draft.deferred_topics)
print(before.conditions.headcount)
```

실행 결과:

```text
applied
50 25000
tentative
('dates',)
32
```

## 함수 안에서 무슨 일이 일어났나

| 코드 구간 | 이번 입력을 처리하는 방법 |
| --- | --- |
| `evidence` 확인 | “대략 50명” 등이 user-1 메시지에 있는지 확인 |
| `values`, `meta` 복사 | 원래 32명인 초안을 보존하고 복사본에 50명·25000원을 준비 |
| `PlanningConditions.model_validate(values)` | 모든 변경을 합친 뒤 타입·최종 날짜 관계 확인 |
| `PlanningDraft(...)` | 인원·참가비의 tentative 근거와 dates 보류를 함께 묶음 |
| `ConditionUpdateResult(...)` | 실제 새 초안을 반환. 입력 before는 여전히 32명 |

이후 agent Node는 이 결과를 보고 “날짜는 나중에 정하고, 약 50명·25,000원을 기준으로 생각해둘게요”처럼 답할 수 있다. 이 답변 생성은 아직 구현하지 않았다. 처리기가 자연어 응답이나 다음 질문을 만들어 붙이지 않는다.

같은 함수에 종료일보다 늦은 시작일을 요청하면 `rejected`와 날짜 설명, 원래 초안을 반환한다. 잘못된 요청을 자동 수정하지 않으므로 다음 단계 LLM이 실제 결과를 보고 설명할 수 있다. 같은 요청을 새 초안에 다시 적용하면 `unchanged`이고, 같은 50명이라도 tentative에서 specified로 바꾸면 `applied`다.

검증은 [test_planning_agent_tools.py](../../tests/test_planning_agent_tools.py) 27개와 AI 전체 597개 통과(2026-10-24). 상세 계약은 [1단계 명세](step-01-state-tool.md)를 참고한다. 다음 2단계에서는 LLM이 이 요청을 만들거나 Tool 없이 대화하는 분기를 LangGraph로 연결한다.
