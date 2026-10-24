# 행사계획 코드 따라가기

오랜만에 읽을 때는 [전체 설계](design.md)의 Node 흐름을 먼저 보고, 아래 단계별 입력 → 코드 → 결과를 따라간다. 1단계는 Tool 처리기, 2단계는 LLM과 LangGraph, 3단계는 실제 UI, 4단계는 기존 기록 검색 Tool 연결이다.

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

1단계 당시 검증은 [test_planning_agent_tools.py](../../tests/test_planning_agent_tools.py) 27개와 AI 전체 597개 통과(2026-10-24). 상세 계약은 [1단계 명세](step-01-state-tool.md)를 참고한다. 이어지는 2단계에서는 LLM이 이 요청을 만들거나 Tool 없이 대화하는 분기를 LangGraph로 연결했다.

## 2단계: 상담하다가 “그렇게 잡자” 하면 상태를 바꾼다

현재 참가비는 25,000원이라고 하자. 아래는 실제 모델 검증에서 나온 흐름이다.

### 첫 번째 턴 — “참가비 3만 원이면 어때?”

1. [graph.py](../../features/planning/agent/graph.py)의 `run_planning_agent_turn()`이 초안과 이번 말을 그래프에 넣는다.
2. [nodes.py](../../features/planning/agent/nodes.py)의 `agent_node()`가 최신 초안·현재 메시지 ID·기준일과 대화 이력을 LLM에 전달한다.
3. 공통 `ainvoke_with_tools()`가 모델에 조건 변경 Tool의 입력 형식을 알려준다. 모델은 사용 가능한 Tool이 있어도 호출하지 않고 상담할 수 있다.
4. 실제 모델은 식비·프로그램 비용의 여유와 참가자 부담을 설명했다. `AIMessage.tool_calls`는 빈 목록이었다.
5. `graph.py`의 조건부 edge가 END를 선택한다. 반환된 참가비는 여전히 25,000원이다.

```text
“3만 원이면 어때?” → agent → 상담 답변 → 종료
현재 참가비: 25,000원 유지 / 모델 호출: 1회
```

### 두 번째 턴 — “일단 그렇게 잡자.”

호출자는 앞선 답변까지 담긴 `history`와 `draft`를 다음 요청에 넣는다. LLM이 직전 대화를 보고 “그렇게”를 참가비 30,000원으로 해석한다.

```python
# 실제 Tool 인자를 이해하기 쉽게 줄인 형태
AIMessage(tool_calls=[{
    "name": "update_event_conditions",
    "id": "이번 호출 ID",
    "args": {"changes": [{
        "op": "SET",
        "change": {"field": "fee_per_person", "value": 30000},
        "status": "tentative",
        "evidence": {"message_id": "이번 사용자 메시지 ID", "quote": "일단 그렇게 잡자."},
    }]},
}])
```

이 데이터는 설명용 축약이며 `AIMessage`를 직접 만들어 실행할 필요는 없다. 실제 호출에서는 모델이 생성한다.

`tool_calls`가 있으므로 edge는 tools로 보낸다. `tools_node()`가 인자를 `UpdateEventConditionsInput`으로 검증한 뒤 **1단계의 `update_event_conditions()`를 호출한다.** 새 초안과 `applied` 결과를 받으면 다음을 함께 반환한다.

```text
draft: 참가비 30,000원·tentative로 갱신
ToolMessage: 이번 Tool 호출 ID에 연결된 실제 실행 결과
```

이제 다시 agent로 돌아간다. 모델이 읽는 것은 **업데이트된 30,000원 초안 + Tool 성공 결과 + 앞선 대화**다. 실제 답변은 “참가비는 일단 1인 3만 원으로 잡아둘게요. 아직 잠정안으로 반영했습니다.”였다.

```text
“일단 그렇게 잡자” → agent → tools → agent → 답변·종료
현재 참가비: 30,000원·잠정 / 모델 호출: 2회
```

전체 연결은 아래 네 줄에서 읽을 수 있다.

```python
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", lambda state: "tools" if state["messages"][-1].tool_calls else END)
graph.add_edge("tools", "agent")
graph.compile()
```

### “왜 반영이 안 됐어?”와 Tool 거절은 어떻게 설명하나

자연어 답변만 저장하지 않고 Tool 호출·결과도 history에 남긴다. 따라서 다음 턴에는 어느 값이 실제 반영됐는지 보고 설명할 수 있다. 새로운 조건이 없으면 Tool을 다시 호출할 필요가 없다.

날짜 충돌로 거절됐을 때도 tools Node는 원래 초안과 이유를 ToolMessage로 준다. 모델은 이를 보고 종료일과 시작일 순서가 맞지 않아 반영하지 않았다고 설명했다. 별도 “설명 의도 분류 Node”나 고정 질문 템플릿을 추가하지 않았다.

실제 날짜 수정 대화에서는 근거 메시지 ID를 잘못 낸 호출이 한 번 거절됐고, 모델이 결과를 읽고 바로잡아 성공했다. 이렇게 오류 수정도 같은 `agent → tools → agent` 흐름 안에서 일어난다. 무한히 반복하지 않도록 한 턴 Tool 시도는 최대 3회다.

## 새 Agent를 직접 호출하기

`be/`에서 아래 코드를 `.venv/bin/python`으로 실행한다. 1단계 예시와 달리 **실제 모델 API를 호출한다.** `.env`가 필요하다.

```python
import asyncio
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.schemas import PlanningConditions, PlanningMessage

async def main():
    first = await run_planning_agent_turn(PlanningAgentTurnInput(
        draft=PlanningDraft(conditions=PlanningConditions(event_type="MT", fee_per_person=25000)),
        current_message=PlanningMessage(id="u1", role="user", text="참가비 3만 원이면 어때?"),
        reference_date="2026-10-24",
    ))
    print(first.reply, first.draft.conditions.fee_per_person)
    second = await run_planning_agent_turn(PlanningAgentTurnInput(
        draft=first.draft, history=first.history,
        current_message=PlanningMessage(id="u2", role="user", text="일단 그렇게 잡자."),
        reference_date="2026-10-24",
    ))
    print(second.reply, second.draft.conditions.fee_per_person)

asyncio.run(main())
```

이 예시와 같은 두 턴은 실제 평가 입력에도 포함된다. 답변 문구는 실행마다 달라질 수 있다.

2단계 당시 그래프·공통 호출 테스트는 26개, AI 전체 623개 통과. 실제 합성 10턴의 상태·Tool 자동 확인은 모두 일치했지만 한 답변에 불필요한 원인 추정이 있었다. [실측과 한계](evaluation.md)를 함께 읽는다. 3단계에서는 테스트 UI가 이 진입점을 호출하도록 연결했다.

## 3단계: 화면의 카드가 바뀌는 순간까지 따라가기

브라우저에서 [테스트 화면](http://127.0.0.1:5174/)을 열고 이야기한다. 실제 확인한 예시:

```text
“MT이고 참가비는 25,000원으로 잡자”
  → 카드: MT, 25,000원
“참가비 3만 원이면 어때?”
  → 상담 답변, 카드: 25,000원 유지
“일단 그렇게 잡자.”
  → Tool로 변경, 카드: 30,000원·잠정
```

[PlanningPlaygroundPage.tsx](../../tests/ui/planning/src/pages/PlanningPlaygroundPage.tsx)의 `send()`가 `draft + history + current_message`를 `/__planning-test/agent/turn`에 보낸다. 서버의 [agent_turn()](../../scripts/planning_playground.py)이 이를 검증해 2단계의 `run_planning_agent_turn()`을 호출한다. 서버에는 대화 세션을 저장하지 않는다.

성공하면 테스트 UI는 `setLast(response.result)` 한 번으로 **초안과 이력을 함께** 바꾼다. 채팅창은 `reply`를 표시하고, [toAgentFacts()](../../tests/ui/planning/src/features/planning/agent-playground.ts)는 `draft.conditions`와 `condition_meta`로 카드를 만든다. 그래서 상담 문장에 3만 원이 등장해도 카드 값이 바뀌지 않는다. 실제 Tool이 30,000원을 반영한 다음 응답에서 값과 잠정 표시가 함께 바뀐다.

화면의 말풍선은 사용자/AI 대화만 보여준다. 다음 요청에 보내는 `history`에는 Tool 호출·결과도 포함된다. 테스트 UI가 이를 단순 말풍선 목록으로 다시 만들면 “왜 반영이 안 됐어?”를 설명할 근거가 없어지므로 반환된 이력을 그대로 전달한다.

“날짜는 아직 모르겠고, 약 50명에 인당 25,000원 생각 중”에는 인원·참가비 잠정 표시와 `나중에 정할 내용: 일정`이 나타났다. “왜 반영이 안 됐을까?”에는 새 조건 질문을 붙이는 대신 실제 반영 상태를 설명했다. 이번 UI에서는 설명에 내부 상태 코드 `applied`가 노출되는 표현이 있었으며, 답변 문체 보완 과제로 남겼다.

연결 실패 때는 `setLast()`를 실행하지 않는다. 실제 서버를 끄고 “45명으로 바꿔줘”를 보내자 기존 50명이 유지됐고, 서버 복구 후 재시도에서 45명으로 바뀌었다. 같은 메시지 ID를 재사용해 사용자 말풍선은 하나만 남았다.

`처리 흐름 보기`를 열면 모델 호출 수와 Tool의 반영/유지/미반영 결과를 볼 수 있다. 실제 화면을 보며 1·2단계 코드와 연결해 이해하는 용도다. 실행 방법·최신 검증·BE/FE 논의할 항목은 [3단계 UI 안내](step-03-ui.md)에 있다.

## 4단계: 과거 기록을 찾고, 사용자가 원하면 올해 계획에 적용한다

현재 참가비 25,000원에서 “2025년 봄 MT 참가비는 얼마였어?”라고 묻는 예시다. 실제 샘플 검색에서는 45,000원이 나왔다.

```text
agent: search_past_events(query="2025 봄 MT 참가비") 선택
  → tools_node: 이름으로 검색 처리기 선택
  → search_past_events: 서버의 동아리 범위·port를 붙임
  → 기존 search_records: 검색어 정리 → 임베딩 → port 검색 → 근거 판단
  ← 45,000원이라는 사실 + 보고서·안내문 출처
  → agent: 결과를 읽고 과거 참가비와 출처 설명
```

핵심 코드는 [record_tool.py](../../features/planning/agent/record_tool.py)의 `search_past_events()`다. **검색 엔진을 새로 만든 것이 아니라 기존 `search_records()` 호출 전후의 입력·결과를 연결한다.** LLM이 만드는 인자는 query 하나이며 동아리 ID와 검색 port는 로컬 서버가 주입한다.

| 어디에서 | 이 예시의 입력 → 출력 |
| --- | --- |
| `agent_tool_schemas()` | 검색이 주입돼 있으면 모델에 두 Tool의 사용법·입력 형식 전달 |
| `tools_node()` | `search_past_events` 이름 확인 → 검색 인자 검증 → 검색 처리기 호출 |
| `search_past_events()` | 질문·현재 행사 종류/시기·서버 동아리 범위 → 기존 retrieval 실행 |
| `RecordLookupResult` | `available` + facts/실제 sources. 현재 초안은 포함하거나 수정하지 않음 |
| `ToolMessage` | 같은 호출 ID에 검색 결과 연결 → agent가 읽고 답변 |
| `AgentReferences` | 구조화된 facts/sources를 참고 카드에 표시. 본문에서 출처를 추출하지 않음 |

이때 **현재 참가비는 25,000원 그대로다.** 검색 결과는 `record_lookup`, 현재 조건은 `draft`로 구분되기 때문이다.

이어서 “올해도 그 금액으로 하자”라고 하면 이전 Tool 결과가 history에 있으므로 LLM이 45,000원을 참조해 `update_event_conditions`를 요청한다. 1단계 처리기가 실제 값을 바꾸고, 그 뒤에 현재 조건 카드가 45,000원으로 바뀐다. FE는 조회하지 않은 턴에 기존 참고 카드를 유지하되 ‘마지막 조회 기준’이라고 표시한다.

검색 상태도 서로 다르다. `not_found`는 검색했지만 근거가 없는 경우, `failed`는 조회 호출 실패다. 자료에 서로 다른 값이 있으면 conflicts를 그대로 전달한다. 어느 상태든 검색 자체가 올해 조건을 바꾸지는 않는다. 혼합 요청에서 먼저 인원을 바꾸고 검색만 일시적으로 실패했다면 바뀐 인원과 조회 실패를 함께 설명할 수 있다.

그래프는 여전히 `agent ↔ tools` 두 Node다. 새 행동을 추가하면서 Tool의 입력·처리기·결과 타입과 이름 분기를 확장한 것이다. 검색의 검색어 정리·근거 판단 모델 호출은 Agent의 `model_calls`와 별개라, 실제 전체 HTTP 호출 수는 [평가 기록](evaluation.md)에서 확인한다.

실제 UI에서도 조회 후 현재 25,000원 유지 → “올해도 그 금액으로 하자” 후 45,000원 반영을 확인했다. 수락 턴의 `record_lookup`은 `null`이다. 재검색하지 않았기 때문이며, FE는 이전 조회 자료를 별도로 보관해 출처 카드를 유지한다. [조회 직후](ui-tests/agent-records-lookup-2026-10-24.png)와 [수락 후](ui-tests/agent-records-applied-2026-10-24.png)를 비교하면 답변에 나온 숫자와 현재 조건이 언제 달라지는지 볼 수 있다.

직접 테스트하는 방법·BE/FE 전달 사항·남은 작업은 [4단계 명세](step-04-record-tool.md)를 참고한다.


## 테스트 화면의 위치와 FE 전달 경계 (#174)

```text
AI 테스트 앱: be/app/ai/tests/ui/planning/ (포트 5174)
 → 자체 Vite 프록시 /__planning-test
 → AI 로컬 API (포트 8011)
 → Agent 결과를 테스트 화면에 표시
 → 상태·실패 사례·필요 계약을 BE/FE 전달 자료로 정리
```

화면·타입·스타일·package/lockfile은 모두 AI 테스트 폴더에 있다. 초기 FE 화면 조각을 참고한 복사본을 보관하지만 제품 `fe/`를 import하거나 빌드에 사용하지 않는다. 제품 FE의 라우트·공용 컴포넌트·타입·프록시에 추가했던 테스트 변경은 제거했다. 실제 UI 구현은 FE팀의 역할이며 이 테스트 앱을 제품 코드로 자동 반영하지 않는다. [독립 실행 안내](../../tests/ui/planning/README.md)를 따른다.
