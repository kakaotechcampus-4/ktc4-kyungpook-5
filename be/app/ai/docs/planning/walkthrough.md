# 행사계획 코드 따라가기

현재 흐름은 `agent/`와 `generation/`을 따른다. 이전 `turn_*`, `lookup.py`, `records.py`, `questions.py`, 조건 추출 `nodes.py`는 [features/planning/legacy](../../features/planning/legacy/README.md)에 있다. 공유 조건 값과 `PlanningMessage`는 `planning/schemas.py`에 남겼으며 현재 코드가 legacy 타입을 가져오지 않는다.

#184에서 공개 함수로 실제 모델을 확인했다. 25,000원 → 30,000원 상담(값 유지) → JSON 저장/복원 → “일단 그렇게 잡자”(30,000원 잠정 반영) → 권유 수락 생성 순서다. [실측 결과](evaluation.md#공개-함수-실제-모델-연결-검증-184-2026-10-25)와 [BE 저장 예시](p1-public-contract.md#13-be-호출과-저장-순서-184)를 함께 읽으면 호출부터 저장까지 연결된다.

공개 경계의 정의 위치는 #183에서 통일했다. **contracts.py(무엇을 주고받는가) → facade.py(무엇을 호출하는가) → features/planning(어떻게 처리하는가)** 순서로 읽으면 된다. 예를 들어 “50명으로 잡자”는 루트 `PlanningChatRequest`로 들어와 `chat_planning`과 기존 Graph/Tool을 거친 뒤 루트 `PlanningPublicResult`로 돌아온다. 오류는 `errors.py`에서 찾는다. 기존 `planning_contracts.py`는 호환용 재공개만 남았다.

오랜만에 읽을 때는 [전체 설계](design.md)의 Node 흐름을 먼저 보고, 아래 단계별 입력 → 코드 → 결과를 따라간다. 1단계는 Tool 처리기, 2단계는 LLM과 LangGraph, 3단계는 실제 UI, 4단계는 기존 기록 검색 Tool 연결이다. 5단계는 권유·계획 생성과 채팅/버튼 HTTP·P2 테스트 화면까지 연결했다.

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

이후 agent Node는 이 결과를 보고 “날짜는 나중에 정하고, 약 50명·25,000원을 기준으로 생각해둘게요”처럼 답할 수 있다. 이 답변 생성은 아래 2단계의 agent Node가 담당한다. 처리기가 자연어 응답이나 다음 질문을 만들어 붙이지 않는다.

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

성공하면 테스트 UI는 응답을 한 번에 채택해 **초안과 이력을 함께** 바꾼다. 채팅창은 `reply`를 표시하고, [toAgentFacts()](../../tests/ui/planning/src/features/planning/agent-playground.ts)는 `draft.conditions`와 `condition_meta`로 카드를 만든다. 그래서 상담 문장에 3만 원이 등장해도 카드 값이 바뀌지 않는다. 실제 Tool이 30,000원을 반영한 다음 응답에서 값과 잠정 표시가 함께 바뀐다.

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

## 5-1에서 정한 흐름: '이 정도면 만들어볼까요?'에서 계획 초안으로

**아래는 5-1에서 잡은 설계 흐름이며 실제 내부 구현과 UI 연결은 뒤의 5-2·5-3 설명으로 이어진다.** [5단계 명세](step-05-generation.md)에 상세 계약을 정리했다.

사용자가 'MT고 약 50명, 인당 25,000원. 날짜는 나중에'라고 했다고 하자. 기존 코드가 이미 하는 일과 앞으로 붙일 일을 나누어 읽으면 쉽다.

| 순서 | 입력 → 거칠 코드 → 결과 |
| --- | --- |
| 1. 조건 모으기 — 구현됨 | 현재 발화 → `agent_node()`가 `update_event_conditions` 요청 → MT·잠정 50명·참가비, dates 보류 |
| 2. 먼저 권하기 — 내부 구현 | 반영된 draft와 대화 → 같은 agent가 권유 판단 → `update_generation_offer(action=offer)`로 기준 조건 기록 → '날짜는 비우고 준비 순서를 먼저 잡아볼까요?' |
| 3. 수락하기 — 내부 구현 | '응, 만들어줘' → agent가 직전 권유와 연결 → `generate_event_plan` 요청. Tool에는 이번 수락 근거와 제안 ID를 전달 |
| 4. 생성 입력 준비 — 내부 구현 | Tool 처리기가 최신 draft·제안 상태 확인 → 현재 조건/사용자 요구/카탈로그/실제 참고 근거로 `PlanGenerationInput` 구성 |
| 5. 초안 만들기 — 내부 구현 | 별도 생성 graph의 `compose_plan`이 구조화 출력 → `validate_plan`이 단계·날짜·출처 등 확인 → 검증된 `EventPlanPreview` |
| 6. 설명·화면 — 로컬 연결 | Tool 결과 → 대화 agent가 초안 설명 → 테스트 UI가 성공 결과를 P2에 표시. 날짜 미정·50명 잠정 유지 |

즉, **대화 Agent는 '지금 무엇을 할까', 생성 graph는 '어떤 계획을 만들까'를 맡는다.** 화면이 P2로 바뀌어도 대화 상대와 행사 조건을 버리지 않는다.

왜 권유 상태를 하나 더 둘까? '응'이 수락한 대상과 그때의 조건을 알기 위해서다. 50명일 때 권했다가 지금 40명으로 바뀌었으면, 옛 제안을 그대로 실행하지 않는다. 반면 '40명으로 바꾸고 바로 만들어줘'라면 조건 변경 성공 후 최신 40명으로 만들 수 있다.

'아직 만들지 말자'에는 보류를 기록하고 같은 조건으로 반복 권하지 않는다. 생성 권유는 빈칸 개수로 강제하지 않으며, 유형만 정해졌더라도 사용자가 기본 준비 순서를 직접 요청하면 일반 초안을 만들 수 있다. 유형도 없으면 어떤 행사인지 먼저 확인한다.

예정된 두 데이터의 차이도 기억하면 좋다. **`PlanningDraft`는 MT·50명 같은 행사 조건**, **`EventPlanPreview`는 장소 알아보기·모집 공지 같은 준비 단계**다. 생성하면서 조건을 임의로 채우지 않고, 단계에 필요한 미정 항목을 따로 알려준다. 생성 실패 시 기존 조건과 이전 성공 초안은 유지한다.

5-2에서 위 내부 Tool·생성 graph를 구현했고 [schemas.py](../../features/planning/agent/schemas.py)에 generation 상태를 추가했다. 바깥 [graph.py](../../features/planning/agent/graph.py)는 `agent`와 `tools`를 유지한다. 5-3에서 화면도 연결했다.

## 5-2①: 채팅과 버튼은 다른 요청, 생성에는 같은 입력

현재 [generation/schemas.py](../../features/planning/generation/schemas.py)에 생성 입력·결과와 권유 상태를 구현했다. 버튼 연결은 아래 5-3 절, 공개 호출은 문서 앞부분의 P1 계약을 따른다.

```python
# 버튼: 클릭 ID만 필요. 가짜 사용자 메시지를 만들지 않는다.
ButtonGenerationTrigger(request_id="click-1")
# 채팅: 이번 메시지 ID와 실제 수락/요청 문구가 필요하다.
ChatGenerationTrigger(request_id="u1", quote="만들어줘")
# 둘은 공통 PlanGenerationInput의 trigger에 들어간다.
```

`PlanGenerationInput`은 `basis_draft + trigger + messages + reference_date + timezone + reference_facts`다. 날짜 없는 MT·50명 입력이면 basis_draft의 날짜는 그대로 null이다. 모델이 요청의 출처를 선택하는 것이 아니라 각 진입점이 정해진 trigger를 만든다.

[generation/offers.py](../../features/planning/generation/offers.py)의 `update_generation_offer()`는 `offer`일 때 조건 복사본과 ID를 만들고, `defer`일 때 이번 발화 근거를 확인해 보류를 기록한다. `same_basis()`는 값·잠정 여부·보류 주제를 비교한다. 같은 50명을 다시 말해 근거 ID만 바뀌었다면 같은 기준이고, 40명으로 바뀌거나 잠정에서 명시로 바뀌면 다른 기준이다.

권유/보류 상태와 마지막 성공 초안은 `PlanningGenerationState`로 묶는다. `condition_change_pending`은 변경이 거절된 뒤 옛 조건으로 조용히 생성하는 것을 막기 위한 표시다. 이 상태는 저장·행사 승인 레코드가 아니다. 테스트 5개에서 요청 구분, JSON 왕복, 기준 비교, 보류 후 재권유 거절과 카탈로그 13개 경계를 확인했다.

## 5-2②: 버튼 진입점에서 공통 생성 graph까지

[generation/entrypoints.py](../../features/planning/generation/entrypoints.py)의 `run_button_plan_generation()`은 클릭 요청을 공통 생성 입력으로 바꾼다. Agent를 호출하지 않으며 권유 ID나 사용자 문구도 만들지 않는다.

```text
ButtonPlanGenerationRequest(request_id="click-1", draft=MT·50명·날짜 미정)
  → ButtonGenerationTrigger(source="button", request_id="click-1")
  → generate_with_context(): 유형·미해결 변경·같은 성공 요청 확인
  → run_plan_generation(): compose_plan → validate_plan
  ← GenerationUpdate(result.status="generated", generation.preview=검증된 초안)
```

[generation/graph.py](../../features/planning/generation/graph.py)의 핵심은 두 Node다. `compose_plan()`은 현재 조건·최근 대화·13개 카탈로그를 JSON 데이터로 전달해 `PlanComposition` 구조화 출력을 받는다. 모델은 code·purpose·일정·예정 행동을 작성하며 현재 조건을 다시 쓰지 않는다.

`validate_plan()`은 포함/제외한 단계가 카탈로그 전체를 빠짐없이 나누는지, 묶음 순서·날짜·허용 행동이 맞는지 검사한다. 그 뒤 코드가 카탈로그의 이름·담당을 붙여 `EventPlanPreview`로 만든다. 과거 자료를 참고한 가정의 `fact_ids=["f1"]`은 전달한 실제 사실의 출처로 바꾼다. 모델이 출처 객체·URL을 새로 쓰지 않는다.

입력의 행사 날짜가 null인데 출력에 날짜가 있으면 `failed`다. null을 유지하면 생성 성공이며 `open_questions`에 행사 날짜가 남는다. 이 목록은 지금 모두 답하라는 채팅 질문이 아니다. `basis_draft`는 입력과 같고 인원 잠정 여부도 유지한다.

`generate_with_context()`는 성공한 preview만 상태에 채택한다. 같은 클릭 ID·같은 기준으로 성공 요청을 다시 보내면 모델 호출 없이 같은 preview를 반환한다. 같은 ID에 다른 조건을 넣으면 재확인을 요구한다. 아직 마지막 성공 한 건만 보관하므로 임의의 오래된 요청 전체를 중복 제거하는 서버 저장소는 아니다. 별도 버튼 HTTP/FE 연결은 아래 5-3 절을 따른다.

### 생성 호출이 긴 JSON을 끝까지 받는 방법 (#176)

입력이 `워크숍 / 약 40명 / 25,000원 / 10월 31일~11월 2일`이면 모델은 여러 준비 단계·일정·행동을 JSON 한 덩어리로 작성한다. 짧은 채팅 답변보다 출력이 길다.

```text
“그렇게하자”
  → agent가 generate_event_plan Tool 선택
  → Tool이 권유·원문·현재 조건 확인
  → run_plan_generation → compose_plan
  → invoke_plan_composition: 생성 전용 모델로 구조화 출력 요청
       max_output_tokens=8192, streaming=True
       조각 수신 → 완성본 조립 → PlanComposition 검증
  → validate_plan: 단계·날짜·행동·실제 출처 검사
  → EventPlanPreview → Agent의 설명 + UI의 P2 화면
```

핵심 설정은 [generation/model.py](../../features/planning/generation/model.py)에 있다. `build_plan_model()`이 공통 `build_chat_model()`에 `max_tokens=8192`, `streaming=True`를 넘긴다. SDK가 실제 Responses 요청의 `max_output_tokens`로 변환한다. `invoke_plan_composition()`은 이 모델을 `ainvoke_structured()`에 주입한다. 생성 graph의 기본 호출과 실제 모델 평가 실행기 모두 같은 생성 전용 설정을 쓴다.

왜 둘 다 필요한가? 현재 게이트웨이는 일반 응답을 2,000토큰에서 끝내고, 그보다 큰 한도의 일반 응답은 거절한다. 추론 토큰도 출력 예산에 포함돼 날짜·행동이 붙은 초안 JSON이 중간에서 끊겼다. 스트리밍으로 길게 받을 수 있게 하되, UI에는 조각을 표시하지 않고 검증된 완성본만 반환한다. LLM의 대화·Tool 선택 방식을 바꾸거나 FE 스트리밍 UI를 요구하는 변경은 아니다.

`ainvoke_structured()`는 최종 완료 상태도 확인한다. 출력 한도로 끝나면 `AIOutputLimitError`, 완료 신호 없이 끊기거나 형식이 틀리면 `AIInvalidResponseError`다. JSON이 우연히 읽혀도 미완성은 실패다. `run_plan_generation()`은 생성/검증 단계와 안전한 실패 분류만 기록한다. 성공한 결과만 `generate_with_context()`가 채택하므로 실패해도 현재 조건과 이전 초안은 유지된다.

실제 관찰은 기존 UI의 “다시 시도해줘” → 13단계 P2 성공(26.68초), 별도 새 대화의 권유 → “그렇게하자” → 생성 성공(25.30초)이었다. 고정 생성 입력 4회는 1/4 → 4/4 성공이었지만 작은 진단 표본이다. 전후 원본·재실행·남은 제한은 [평가 기록](evaluation.md)을 읽는다.

## 5-2③: 채팅의 권유 → 수락 → 생성 결과를 따라가기

예시의 시작 상태는 `MT / 약 50명 / 참가비 25,000원 / 날짜 미정`이다. 실제 테스트에서 대화 모델의 선택을 아래 순서로 대체하고 두 LangGraph를 실행했다. **실제 LLM을 쓴 5-3 관찰은 아래 절과 평가 기록에 별도로 남겼다.**

```text
1. AIMessage.tool_calls: update_generation_offer(action="offer", reason="날짜 없이 준비 순서 가능")
2. tools_node → update_generation_offer()
   generation.offer = { id: 코드가 생성, status: pending, basis_draft: 현재 조건 복사 }
3. agent가 결과를 읽고 "날짜를 비우고 준비 순서를 먼저 잡아볼까요?"로 이번 턴 종료
4. 다음 입력: "응, 만들어줘" + 이전 draft/history/generation
5. AIMessage.tool_calls: generate_event_plan(quote="응, 만들어줘", offer_id=직전 ID)
```

[agent/generation_tools.py](../../features/planning/agent/generation_tools.py)의 `generate_event_plan()`이 실제로 검사하는 핵심 부분은 다음과 같다. 설명용으로 줄인 코드다.

```python
evidence = MessageEvidence(message_id=request.current_message.id, quote=arguments.quote)
if not valid_evidence(evidence, request.current_message):
    return clarify("이번 사용자 발화 근거가 필요해요")
if arguments.offer_id is not None:
    # 존재·pending·ID를 확인한 다음
    if not same_basis(offer.basis_draft, draft):
        return clarify("권유 뒤 조건이 바뀌었어요")
shared = PlanGenerationInput(basis_draft=draft, trigger=ChatGenerationTrigger(...), ...)
return await generate_with_context(shared, state, generate=generate)
```

`quote`는 모델이 원문에서 선택하고, 메시지 ID는 코드가 현재 요청에서 붙인다. ID를 복사하게 하지 않으므로 모델의 한 글자 오타가 유효한 수락을 막지 않는다. 원문에 없는 문구와 오래된 권유 검사는 유지한다.

근거 검사에 통과하면 버튼과 동일한 `generate_with_context()` → 생성 graph로 이어진다. Tool 결과에는 `status=generated`와 실제 preview가 들어가고 다시 대화 Agent에 전달된다. 마지막 답변은 그 결과를 읽고 작성한다. 코드가 '만들었어요'를 고정 문구로 붙이지 않는다.

현재 결과의 두 필드를 구분하면 이해하기 쉽다.

```text
generation_result = 이번 턴 생성 시도의 결과. 새 시도가 없으면 null
generation.preview = 마지막 성공 계획. 실패하거나 상담만 한 턴에도 유지
preview_is_current = 마지막 계획이 지금 조건과 맞고 미해결 변경도 없는가
model_calls = 대화 Agent 호출 수 / generation_model_calls = 생성 내부 호출 수
```

테스트의 수락 턴은 대화 모델 2회(선택·답변), 생성 모델 1회였다. 실제 HTTP 재시도와 응답 시간 측정값은 아니다. 한 턴 Tool 시도 3회 상한은 조건·검색·권유·생성에 공통으로 적용하고, 생성 graph 안에서는 자동 수정 반복을 하지 않는다.

### 수정·실패는 어떻게 다루나

사용자가 '40명으로 바꾸고 바로 만들어줘'라고 하면 같은 tools Node에서 조건 변경을 먼저 실행하고 다음 생성 Tool이 최신 40명을 읽는다. 직접 요청이므로 offer_id를 요구하지 않는다. 반면 50명일 때의 권유 ID를 40명으로 바뀐 뒤 수락하면 확인을 요구한다.

'시작일을 종료일보다 뒤로 바꾸고 만들어줘'의 날짜 변경은 거절된다. `condition_generation_state()`가 `condition_change_pending=True`, `pending_condition_fields=("start_date",)`를 남기고 생성은 확인을 요구한다. 이후 참가비만 바꿔도 start_date 문제는 남는다. 같은 필드를 유효하게 고치거나, 사용자가 현재 남은 날짜로 만들겠다고 명시해야 해결된다.

40명으로 바꾼 뒤 생성 호출만 실패하면 40명은 보존하고 이전 성공 preview도 유지한다. 이때 `preview_is_current=False`로 오래된 기준임을 구분한다. 원본 입력 객체는 바꾸지 않는다. 설정·권한·예상하지 못한 예외는 정상 실패로 숨기지 않고 위로 전달한다.

### 내부 진입점과 직접 검증

- 채팅: `run_planning_agent_turn(request, generate=run_plan_generation)`. 생성 기능을 주입하지 않으면 새 두 Tool은 모델에 공개하지 않는다.
- 버튼: `run_button_plan_generation(ButtonPlanGenerationRequest(...))`. 대화 Agent의 의도 해석과 가짜 HumanMessage를 거치지 않는다.
- 위 두 함수는 내부 진입점이다. 현재 공개 facade는 `chat_planning`과 `generate_planning_preview`로 이 경로를 연결한다. 아래 테스트 API와 제품 HTTP는 별개이며, 제품의 저장과 권한, HTTP/FE 연결은 #187에서 진행한다.

`be/`에서 API 없이 확인할 수 있다.

```sh
.venv/bin/python -m pytest app/ai/tests/test_plan_generation_contracts.py app/ai/tests/test_plan_generation_graph.py app/ai/tests/test_planning_agent_generation.py -q
```

신규 39개(요청/권유 5, 생성/버튼 22, 대화 연결 12)와 이번 커밋 대상의 AI 회귀 680개가 통과했다. 테스트는 모델 응답을 대체한 실제 graph 실행이며, 생성 품질·친근함·자율 선택의 정확도 검증은 아니다. 실제 모델과 P2 UI 검증은 아래 5-3 절과 평가 기록을 따른다.

## 5-3: 두 API의 실제 응답이 같은 P2에 표시된다

[PlanningPlaygroundPage.tsx](../../tests/ui/planning/src/pages/PlanningPlaygroundPage.tsx)의 `session`은 `draft + history + generation`이다. `messages`는 화면 말풍선 목록이며 SDK Tool 이력인 history와 구분한다.

```text
send("초안 만들어줘")
  → execute({source: "chat", body: 세션 + current_message})
  → POST /__planning-test/agent/turn
  → 대화 Agent → 생성 Tool → 생성 graph
  ← reply + draft/history/generation
  → 세션 전체 채택 + AI 말풍선 추가 + generated이면 P2

generate() — '다음: 흐름 만들기' 클릭
  → execute({source: "button", body: 세션 + request_id})
  → POST /__planning-test/agent/generate
  → 버튼 내부 함수 → 생성 graph
  ← generation + 생성 결과
  → generation만 채택, history/말풍선 유지 + generated이면 P2
```

이 경로에서 버튼 요청은 current_message가 없다. 로컬 API는 `validate_planning_history()`로 채팅과 같은 이력 검사를 하고, `plan_messages()`와 `latest_reference_facts()`로 실제 문맥·최근 근거만 준비한다. 클릭을 사용자 말풍선으로 만들지 않는다.

[AgentPlanPreview.tsx](../../tests/ui/planning/src/features/planning/components/AgentPlanPreview.tsx)가 검증된 preview를 테스트 앱 안의 StepFlow에 전달한다. [generation-playground.ts](../../tests/ui/planning/src/features/planning/generation-playground.ts)의 `toPreviewSteps()`는 서버 이름·묶음·담당·목적·예정 행동을 표시 타입으로 바꾼다. 미정 날짜는 '미정'이다. 수정 콜백을 전달하지 않아 수정 버튼도 보이지 않는다. 제외 단계의 FE/BE 코드 차이는 명시적인 변환표로 이름을 찾는다.

버튼 활성화는 행사 유형이 있고 미해결 변경이 없는지 확인한다. 권유 상태가 deferred여도 사용자가 직접 누르면 요청할 수 있다. 전송 중에는 입력·초기화·다음 버튼을 잠그고, 버튼 요청에는 별도 생성 중 화면을 표시한다. 단계별 진행률을 알 수 없는 상태에서 가짜 퍼센트는 표시하지 않는다.

네트워크 실패는 이전 세션·preview를 유지하고 요청 전체의 스냅샷을 보관한다. '같은 요청 재시도'는 같은 ID·조건·이력을 보내고, 재시도 중 다른 요청은 잠근다. 정상 응답 안의 생성 실패는 채팅의 유효한 조건 변경을 유지한 채 설명하며 새 요청으로 다시 생성할 수 있다. 대화로 돌아가 조건을 바꾸면 `previewIsCurrent()`가 이전 초안의 기준 차이를 표시한다.

진단 JSON은 반환된 초안·이번 사용자 메시지 ID/텍스트·이번 턴 Tool 인자와 실행·호출 수만 선별한다. SDK 이력은 다음 요청에 그대로 전달하지만 화면에 응답 메타정보·비텍스트 블록을 덤프하지 않는다. 실제 브라우저·모델 검증 결과와 제한은 [평가 기록](evaluation.md)에 남긴다.

실제 UI에서 50명·25,000원 잠정 조건 → 버튼 생성(20.21초, 이력 8개 유지) → 40명 변경/생성 보류 → 채팅 생성(20.04초, trigger=chat)을 확인했다. 전송 실패 때는 같은 preview ID가 보존됐고 같은 클릭 요청 재시도에 성공했다. [화면 개요](ui-tests/agent-generation-chat-overview-2026-10-24.jpg)와 [입력·상태 기록](ui-tests/agent-generation-trace-2026-10-24.json)을 함께 보면 상태가 언제 바뀌는지 확인할 수 있다.

실제 모델에서 '날짜와 장소는 나중에'의 근거를 재작성해 거절된 사례도 있었다. 검사 규칙을 느슨하게 하지 않고 원문 복사·재시도 지침만 보완했다. 동일 6턴의 복합 기대 기준은 1/6→4/6이었지만, 작은 합성 표본이며 권유 타이밍과 JSON 파싱의 불일치가 남아 있다. 연결이 동작한다는 것과 모든 모델 답변이 올바르다는 것은 구분한다.


### 짧은 수락의 실제 실패 → 코드 보완 → 같은 문장으로 생성

```text
이전 권유: “날짜는 미정으로 두고 준비 순서 초안을 만들까요?” (pending)
입력: “응, 그 초안 만들어줘.”
v4: 모델이 이번 메시지 UUID를 한 글자 잘못 복사 → 원문 근거 검사 거절 → P1 유지
v5: 모델은 quote와 offer_id 선택 → 코드가 현재 메시지 ID 주입 → 검사 → 생성 → P2
결과: 약 50명·25,000원 잠정, 날짜·장소 미정, 12단계 초안 (23.74초)
```

여기서 바꾼 것은 **생성 Tool의 입력 경계**다. 생성 요청인지와 어떤 제안을 수락했는지는 여전히 LLM이 해석한다. 메시지 ID는 이미 요청에 있으므로 모델이 다시 쓸 이유가 없다. `GenerateEventPlanInput.quote` → `MessageEvidence(current_message.id, quote)` → `valid_evidence()` → `PlanGenerationInput`으로 흐른다. 조건 변경 Tool·권유 보류 Tool의 기존 `MessageEvidence` 계약까지 바꾼 것은 아니다.

실제 Tool 인자는 `{quote: "응, 그 초안 만들어줘.", offer_id: 직전 pending ID, use_current_conditions: false}`였다. 생성된 preview의 `trigger.request_id`는 이번 사용자 메시지 ID와 일치했다. 실패 뒤 같은 세션에서 같은 문장을 새 턴으로 보낸 1회 관찰이며, 성공률 일반화는 하지 않는다. [전후 근거](ui-tests/agent-generation-acceptance-2026-10-24.json)와 [완료 화면](ui-tests/agent-generation-acceptance-2026-10-24.jpg)을 보존했다.


## 테스트 화면의 위치와 FE 전달 경계 (#174)

```text
AI 테스트 앱: be/app/ai/tests/ui/planning/ (포트 5174)
 → 자체 Vite 프록시 /__planning-test
 → AI 로컬 API (포트 8011)
 → Agent 결과를 테스트 화면에 표시
 → 상태·실패 사례·필요 계약을 BE/FE 전달 자료로 정리
```

화면·타입·스타일·package/lockfile은 모두 AI 테스트 폴더에 있다. 초기 FE 화면 조각을 참고한 복사본을 보관하지만 제품 `fe/`를 import하거나 빌드에 사용하지 않는다. 제품 FE의 라우트·공용 컴포넌트·타입·프록시에 추가했던 테스트 변경은 제거했다. 실제 UI 구현은 FE팀의 역할이며 이 테스트 앱을 제품 코드로 자동 반영하지 않는다. [독립 실행 안내](../../tests/ui/planning/README.md)를 따른다.

## 응답 시간은 어떻게 비교할까? (#196)

같은 MT 조건에서 사용자가 “응, 만들어줘.”라고 답하는 경우와 버튼을 누르는 경우를 생각해 보자.

```text
같은 JSON 상태를 매번 새로 복원
  채팅 → chat_planning()
           → Agent의 해석 → 생성 Tool → 생성 Graph → Agent의 설명 → 반환
  버튼 → generate_planning_preview()
           → 생성 Graph → 반환

각 공개 함수의 호출 직전부터 반환/예외 직후까지 측정
  → 사례별 결과와 실패를 기록
  → 성공률과 성공 요청의 p50/p95 확인
```

채팅 전체가 더 오래 걸려도 생성 모델 자체가 느려졌다는 뜻은 아니다. 내부 `compose_plan()`과 `validate_plan()` 시간, 대화 모델 호출을 따로 봐야 이유를 알 수 있다. 생성 Graph는 전체 시간 안에 포함되므로 두 시간을 다시 더하지 않는다.

일반 상담과 인원 변경도 별도 사례로 둔다. 한 번 잰 숫자 대신 같은 입력으로 반복하고, 실패를 빼고 성공률을 계산하지 않는다. 상세 사례, 반복 횟수와 통계 규칙은 [응답 시간 기준 측정](latency-baseline.md)에 있다. 현재는 고정 입력과 전체 요청 시간의 반복 실행기까지 구현했다. 세부 구간 관측, p50/p95 집계와 실제 모델 기준값은 후속이다.

### 예시: 인원을 60명으로 바꾸는 요청을 반복한다

```text
고정 planning_latency.json
  조건: MT / 50명 / 25,000원 / 날짜 미정
  이력: 권유 Tool 호출과 결과, 마지막 “초안을 만들까요?” 답변
  상태: pending offer 있음, 생성한 초안 없음

① make_request(C2): 같은 JSON을 새로 복원
   이번 발화: “예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마.”
② run_session(): started 이벤트 기록
③ measure_attempt(): 시계 시작 → chat_planning() 호출 → 반환 즉시 시계 종료
④ inspect_result(): headcount가 60인지, 나머지 조건은 유지됐는지 검사
⑤ finished 이벤트: 시간 + 검사 결과 + 실제 반환 결과 기록

다음 C2 반복 → ①의 50명부터 다시 시작
60명으로 바뀐 next_state를 다음 반복에 전달하지 않는다.
```

[planning_latency_inputs.py](../../scripts/planning_latency_inputs.py)의 `make_request()`는 매번 고정 JSON에서 state를 복원한다. request_id와 이번 message_id만 고유하게 만들고 날짜, 조건, 이력과 권유는 유지한다. G2라면 message가 없는 `PlanningPreviewRequest`를 만든다. 기존 성공 초안을 재사용하지 않으므로 같은 생성 경로를 다시 실행할 수 있다.

```python
state = parse_resume_state(fixture.resume_state.model_dump_json())
# C1/C2/G1: 이 state로 PlanningChatRequest를 만든다.
# G2: 같은 state로 PlanningPreviewRequest를 만든다.
```

[measure_planning_latency.py](../../scripts/measure_planning_latency.py)의 `measure_attempt()`는 다음 경계를 지킨다. `await call(request)`에서 실제 공개 함수와 기존 Graph가 실행된다. 타이머가 멈춘 다음 결과를 직렬화하고 검사하므로 파일 저장과 검사 시간은 요청 시간에 섞이지 않는다.

```python
started = clock()
result = await call(request)
elapsed = (clock() - started) / 1_000_000
# 여기부터 결과 계약 검사 → inspect_result() → 파일 기록
```

실제 코드는 예외와 취소에서도 시간을 남긴다. [planning_latency_checks.py](../../scripts/planning_latency_checks.py)의 `inspect_result()`는 답변 문구가 아닌 조건과 상태를 검사한다. “60명으로 반영했어요.”라고 답했지만 headcount가 50이면 실패다. 초안 생성을 요청했는데 정상 답변만 하고 생성하지 않은 경우도 실패다. 실패한 요청을 성공할 때까지 다시 실행하지 않고 다음 사례로 진행한다.

실행 결과는 새 폴더의 `fixture.json`, `session.json`, `attempts.jsonl`이다. JSONL에는 같은 attempt_id의 started/finished가 각각 한 줄씩 생긴다. 앞 기록만 남았다면 중간에 끝난 요청이므로 완료로 간주하지 않는다. 모델 없는 입력 확인 명령과 실제 모델을 사용하는 명령은 [실행 방법](latency-baseline.md#모델-없이-입력과-순서-확인)을 구분해 참고한다.
