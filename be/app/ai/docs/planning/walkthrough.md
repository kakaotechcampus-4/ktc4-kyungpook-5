# 행사계획 코드 따라가기

## 처리 중 진행 알림 (#266, #279)

BE가 `chat_planning(request, progress=port)` 또는
`generate_planning_preview(request, progress=port)`를 호출하면 실제 작업에 맞춰
`port.progress(PlanningProgress)`가 실행된다. 포트를 생략하면 기존 호출 방식을 유지한다.
BE의 SSE 경로(`services/planning_stream.py`, #284)가 이 알림을 `progress`·`reply_delta` 이벤트로 보낸다. 제품 FE는 `features/planning/stream.ts` → `hooks.usePlanningChat` → `PlanChat`에서 진행 줄과 답변 조각을 그린다(#285).
화면은 한 턴의 진행 줄을 토리 답변과 한 덩어리로 묶고, 답변이 끝난 뒤에도 답변 위에 남긴다(#290, `features/planning/turn.ts`). 진행 줄은 저장하지 않으므로 새로고침하면 답변만 남는다.
보내자마자 토리 자리에 입력 중 말풍선(점 세 개)이 뜨고, 답변 첫 조각이 오면 같은 말풍선이 글자로 바뀐다. 진행 중인 줄은 글자가 옅어졌다 진해지고, 완료되면 같은 자리에 체크가 나타난다. 답변이 저장된 뒤 줄이 2개 이상이면 “처리한 작업 2개” 한 줄로 접히고 눌러서 펼칠 수 있다(#295, `components/PlanChat.tsx`).
검색이 정상으로 끝났지만 맞는 기록이 없으면 `search_finished/empty`와 “맞는 기록이 없었어요”가 오고, 화면은 체크 대신 회색 대시로 남긴다. 검색 실패(`failed`)와 구분한다(#300).
답변이 저장되면(done) 오른쪽 「지금까지 정한 것」에서 값이나 상태가 바뀐 칸만 옅은 파란 배경이 1.5초 동안 사라진다. 보낼 때 패널과 done 결과(`PlanViewOut.draft`)를 비교한다(`features/planning/factFlash.ts`, `hooks.usePlanningChat`). 「일정」 칸은 시작일·종료일을 함께 보이고, 진행 줄도 “일정 2026년 12월 5일~6일”로 묶는다(#300).
토리 답변 글은 모델이 쓴 원문 그대로 저장되고, 화면이 그중 굵게(`**`)·목록(`- `, 들여쓴 하위 목록)·빈 줄 문단만 모양으로 바꿔 그린다. 받는 중에도 닫히지 않은 `**` 뒤를 굵게 두어 별표가 보였다 사라지지 않는다(#304, `features/planning/replyText.ts`).

예: “인원은 40명, 일정은 12월 5일부터 6일까지로 해 줘. 작년 MT 숙소 기록도 찾아봐 줘”(실제 모델, 로컬 2026-11-05)

```text
작업 줄   ✓ 예상 인원 40명 · 일정 2026년 12월 5일~6일 반영했어요
          – 맞는 기록이 없었어요                        ← search_finished/empty
패널      예상 인원 40명, 일정 12/5 – 12/6 두 칸만 강조   ← 저장된 답변이 그려진 순간 켜지고 1.49초 뒤 꺼짐
```

예: “예상 인원을 60명으로 바꾸고 초안 만들어줘”:

1. 모델이 조건 변경 Tool을 쓰기 시작하면(첫 조각) `call_agent_model`이
   `condition_started/running`과 “조건을 반영하고 있어요”를 보낸다(#297).
   `agent/tools.py`가 조건을 검증한 뒤 `nodes.tools_node`가 같은 Tool 호출 ID로
   `condition_applied/completed`와 “예상 인원 60명 반영했어요”를 보낸다.
   거절·같은 값이면 `condition_applied/skipped`를 보낸다. 화면은 그 줄을 답변이 시작될 때 지운다.
   예: "…참가비는 20000원" → [검색, 참가비 변경]에서 참가비가 거절되고(검색 결과 전) 모델이 다시
   요청하면, 새 `condition_started`가 처음 줄의 자리를 이어 써 줄이 사라졌다 다시 생기지 않는다(#299).
2. `generation/entrypoints.generate_with_context`는 생성 차단과 성공 결과 재사용을 확인한다.
   실제 생성이 필요할 때만 `generation_started/running`을 보낸다.
3. 생성 및 기준 조건 검증 후 같은 `operation_id`로 `generation_finished`를 보낸다.
   성공은 `completed`, 실패는 `failed`이며 기존 반환 결과는 유지한다.
4. 기존 Agent 답변 작성 → 상태 직렬화 → 공개 결과 반환을 거친다. 저장은 여전히 BE가 맡는다.

`progress.py`의 순수 함수가 검증 결과로 문구를 만들며, `notify`가 알림 포트의 일반 오류를
원문 없이 기록한다. 검색은 실제 호출 직전에 시작을 알리고 자료 없음과 실패를 구분한다.
진행 이벤트는 대화 이력이나 다음 상태 JSON에 넣지 않는다. 단위 테스트는
`tests/test_planning_progress.py`에서 이벤트 순서·거절·재사용·알림 실패와 결과 보존을 확인한다.

### 답변을 쓰는 동안 전달하기 (#280)

`agent.graph`는 기존처럼 최종 상태를 반환한다. 선택적 포트가 있으면 `call_agent_model`이
`llm.astream_with_tools`를 호출한다. 포트가 없으면 `ainvoke_with_tools`를 유지한다.

“인원을 60명으로 바꿔줘” → 첫 호출의 Tool 첫 조각에서 시작 알림(`ReplyStream`의 `on_tool_start`) →
Tool 조각을 온전히 조립·검증 → 조건 변경 실행 →
진행 완료 알림 → 다음 호출의 final_answer 블록을 `reply_delta`로 전달 → SDK 메시지 조립 →
기존 `capture_turn_state`로 저장 상태 반환 순서다. Tool은 미완성 조각으로 실행하지 않는다.

`llm_stream.ReplyStream`은 블록별 phase를 합친 상태에서 답변만 선택한다. commentary와
추론은 표시하지 않으며 phase가 없으면 완료 후 답변을 한 번에 보낸다. 연결이 끊기거나
답변 뒤 Tool이 나타나면 `reply_reset`으로 임시 표시를 비운다. completed 없는 수신은 실패다.
`assembled_message`는 전송용 index와 빈 annotations 차이만 맞춘다. `final_answer_text`는
invoke/stream 공통으로 최종 답변을 선택하며 원본 content는 이력에 남긴다.

실제 공급자 8회 관찰과 한계는 [스트림 형태 확인](evaluation-results/planning-stream-probe-2026-11-04/README.md),
고정 응답 검증은 `tests/test_planning_stream.py`에 있다. 제품 화면 연결은 #285에서 했다(맨 위 절 참고).

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

제품 연결(#235, #236)은 `services/planning_service.py:chat`에서 `app.ai.chat_planning`
공개 함수에 동아리 범위의 `PostgresRecordSearch`를 주입한다. 아래 검색 경로는 그대로
사용하고, `_view_out`이 구조화 사실과 출처까지 제품 DTO로 옮긴다. `_save_turn`은
조건·답변·Agent 상태와 함께 `Conversation.last_record_lookup`을 저장한다.
GET 계획 화면의 `lastRecordLookup`은 이 스냅샷을 읽으며 AI를 호출하지 않는다.
이번 턴 검색이 없으면 기존 스냅샷을 유지하고, 새 검색이 실패하거나 근거를 못 찾으면
그 새 상태로 바꾼다. AI 이력은 여전히 다음 대화·버튼 생성용이고 화면 카드 복원과
별개다. 제품 출처 카드의 FE 구현은 아직 후속이며 아래 사진은 독립 테스트 UI다.

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

'아직 만들지 말자'에는 보류를 기록하고 같은 조건으로 반복 권하지 않는다. 유형과 일정·인원·장소의 답변 여부를 공통 readiness에서 확인한다. 각 주제는 실제 값 또는 명시 보류로 답할 수 있고, 모두 확인된 후 사용자가 생성 요청을 할 수 있다.

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

### 모델이 고를 수 있는 단계 코드는 몇 개인가? (#276)

13개다. 단계 코드 목록 `StepCode`(`app.core.enums`)에는 17개가 있지만, 그중 `CANCEL_*` 4개는 운영 중 행사를 취소할 때 쓰는 코드라 계획 카탈로그에 없다. 생성 모델의 출력 형식([generation/schemas.py](../../features/planning/generation/schemas.py)의 `ModelStep`, `ModelExcludedStep`)은 `code` 칸에 카탈로그 13개(`PLANNING_STEP_NAMES`의 키)만 허용한다.

17개를 그대로 보여 주던 때(`planning-generation-v1`)에는 아래처럼 실패했다.

```text
생성 모델 출력 (v1, 11-04 실측)
  steps          = 카탈로그 13개 전부
  excluded_steps = CANCEL_NOTIFY_PARTICIPANTS, CANCEL_VENUE, CANCEL_REFUND, CANCEL_RECORD
                   "현재 취소 조건이 없으므로 … 포함하지 않습니다."
validate_plan(): 넣은 13 + 뺀 4 = 17 ≠ 카탈로그 13 → catalog_partition 거절 → 사용자는 "초안이 검증을 통과하지 못했어요"

v2: 출력 형식에 CANCEL_*가 없다 → 같은 사례 30번 모두 13개 안에서만 고르고 통과
```

생성 모델 요청은 스트리밍이라 LangChain이 형식을 `strict: true`로 보낸다. 그래도 모델이 형식 밖 코드를 쓰면 `compose_plan()`의 형식 확인에서 출력 형식 실패(`invalid_output`)가 된다. 공개 계약(`contracts.py`)과 저장 형식의 `code`는 그대로 `StepCode`다. #239 재검사 도구는 예전 실패 원본을 읽어야 하므로 v1 형식(`scripts/generation_output_v1.py`)으로 읽는다. 측정은 [평가 기록](evaluation.md)에 있다.

### 제외한 단계의 이름은 누가 붙이나? (#198)

예를 들어 생성 모델이 사전 수요 조사를 제외했다고 하자. 이 선택이 적절한지와 별개로, 화면에서 `DEMAND_SURVEY`라는 코드만 보여 주면 운영진이 이해하기 어렵다. 모델이 고정 이름을 다시 작성할 필요도 없다.

```text
① LLM의 구조화 출력: PlanComposition.excluded_steps
   {"code": "DEMAND_SURVEY", "reason": "이미 참여 의사를 확인한 행사여서 제외했어요."}

② validate_plan(): 포함/제외 목록과 기존 계획 규칙 검사
   → BY_CODE[item.code].name 조회
   → ExcludedPreviewStep(code=..., name="사전 수요 조사", reason=...)

③ 최종 EventPlanPreview.excluded_steps
   {"code": "DEMAND_SURVEY", "name": "사전 수요 조사", "reason": "이미 참여 의사를 확인한 행사여서 제외했어요."}

④ BE가 제품 응답에 매핑 → FE가 name과 reason을 표시
   사전 수요 조사
   이미 참여 의사를 확인한 행사여서 제외했어요.
```

핵심 코드는 [validate_plan()](../../features/planning/generation/graph.py)의 아래 부분이다. LLM이 고른 코드와 이유를 그대로 두고 이름만 붙인다. 채팅 생성과 버튼 생성 모두 같은 Node를 지나므로 결과 형식도 같다. 생성 모델 호출은 기존 1회다.

```python
excluded_steps = tuple(ExcludedPreviewStep(
    code=item.code, name=BY_CODE[item.code].name, reason=item.reason,
) for item in composition.excluded_steps)
```

이름의 원본은 공통 [planning_catalog.py](../../planning_catalog.py)의 `PLANNING_STEP_NAMES`다. 포함 단계와 제외 단계 모두 이 목록을 읽는다. 공개 [contracts.py](../../contracts.py)는 내부 Graph에 의존하지 않고 같은 이름 목록을 사용한다. 모델용 `ModelExcludedStep(code, reason)`(#276부터 code는 카탈로그 13개만)과 최종 화면용 `ExcludedPreviewStep(code, name, reason)`을 나눠, LLM 출력 스키마와 프롬프트는 유지했다.

**예전에 저장한 JSON에는 name이 없는데 괜찮을까?** 공개 타입의 `restore_missing_name()`이 누락된 이름만 고정 목록으로 보완한다. `parse_resume_state()`로 복원하거나 공개 요청의 `resume_state`에 dict를 넣는 두 방식 모두 적용된다. 버전 1을 유지하며 기존 초안 ID, 조건, 제외 이유와 대화 이력을 보존한다. 이름이 명시돼 있는데 틀렸거나 코드가 유효하지 않으면 오류를 반환한다. 모델을 다시 부르거나 상태를 초기화하지 않는다.

이 기능은 최초 생성 결과를 읽기 쉽게 만드는 보완이다. P1에 단계 편집 Tool을 추가한 것이 아니며, P2의 사용자 삭제/복원과 AI 영향 검토는 별도 범위다. 테스트 UI의 표시와 사진은 [검증 기록](evaluation.md#제외-단계-이름과-저장-호환-198-2026-10-28)에 있다. 실제 제품 BE/FE 연결은 #187에서 확인한다.

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

## 생성 전 재확인 반복을 비교하기 (#239)

예를 들어 30명일 때 권유한 뒤 인원만 40명으로 바꾸었다고 하자. 예전 권유는 여전히 30명 기준이고, 현재 draft와 변경 이력은 40명 기준이다. 이 상태에서 “최신 조건으로 초안 만들어줘.”와 버튼을 비교한다.

```text
같은 저장 JSON을 두 번 독립 복원
  ├─ 채팅: chat_planning → Agent의 생성 Tool 선택 → 권유/근거 검사 ┐
  └─ 버튼: generate_planning_preview → 공통 최소 조건 검사         ├→ 생성 Graph
```

`scripts/check_planning_generation_requests.py`의 `build_fixture()`는 공개 함수와 실제 조건/권유 처리기에 고정 대화 응답을 주입해 세 상태를 만든다. `current_offer`는 정상 권유, `changed_headcount`는 30→40명 뒤 옛 권유, `specified_dates`는 같은 일정의 잠정→명시 변경 뒤 옛 권유다. 최초 작성에 외부 모델을 사용하지 않았고 저장본은 `tests/fixtures/eval/planning_generation_requests.json`이다. 실제 멘토 세션을 복원한 것은 아니다.

`make_request()`는 매번 그 JSON에서 새 객체를 만든다. `attempt()`는 공개 함수를 실제 실행하고 기존 #196 관측기로 대화/생성/검증 구간을 기록한다. `capture_tools()`는 합성 Tool 요청과 처리 상태만 선별해, 최종 답변이 예외로 끝나도 직전 생성 요청을 확인할 수 있게 한다. 모델 응답의 추론 블록이나 공급자 오류 원문을 저장하지 않는다.

고정 응답 검사에서는 오래된 `offer_id`를 넣으면 생성 0회, 같은 새 요청에 ID를 넣지 않으면 생성 1회가 되는 분기를 비교한다. 이는 검사가 지켜지는지 확인하는 방법이고 실제 모델의 잘못된 선택을 관찰한 결과는 아니다. 실제 모델에서는 세 상태·두 경로를 3회씩 번갈아 호출하며, 결과를 기대값으로 고치거나 실패 표본을 대체하지 않는다.

`be/`에서 실행한다.

```sh
# 설정/모델 없이 입력과 18개 예정 요청 확인
.venv/bin/python -m app.ai.scripts.check_planning_generation_requests --dry-run
# 실제 모델. 기존 폴더를 덮어쓰지 않도록 새 경로를 사용한다.
.venv/bin/python -m app.ai.scripts.check_planning_generation_requests --output-dir /tmp/generation-requests-new
```

`session.json`은 모델·설정의 공개 가능한 항목·코드/입력 해시·예정/완료 수와 요약이다. `attempts.jsonl`은 시작/종료, Tool 인자/처리 결과와 구간 관측을 가진다. 입력을 고정했더라도 두 모델 응답은 달라질 수 있으므로 “버튼 성공·채팅 실패”만으로 해석 실패를 확정하지 않는다. 생성에 진입했는지와 그 뒤 어느 구간에서 실패했는지 먼저 본다. 실제 관찰과 한계는 [평가 기록](evaluation.md)에 별도로 남긴다.

2026-11-03 실제 luna 기본 비교는 18요청 중 16건 생성 성공이었다. 인원 변경 채팅 2건은 다음 흐름이었다.

```text
현재 워크숍·40명 + 30명일 때의 옛 권유 + “최신 조건으로 초안 만들어줘.”
  → generate_event_plan(quote=이번 원문, offer_id=null)
  → 생성 모델: 구조화 초안 작성
  → validate_plan: invalid_plan으로 거절
  → generation_result.failed, 현재 조건과 다음 상태 보존
  → Agent: 실제 실패를 설명
```

여기서는 새 요청을 올바르게 해석했고 생성에도 진입했다. 코드의 옛 권유 차단 검사 때문에 실패한 것이 아니다. 기본 기록은 어느 세부 규칙에 걸렸는지 남기지 않아 그 두 응답의 상세 원인은 미확인이다. 이 결과와 주입 응답의 재확인 반복을 섞지 않으며, 실제 mini나 제품 화면 오류를 해결했다고 설명하지 않는다.

### 다음 진단: 불합격한 초안을 그대로 재검사한다 (#239)

현재는 시험 결과에 “불합격”만 적혀 있는 상황과 비슷하다. 다음에는 “3번 항목의 날짜가 조건과 다름, 기대값은 11월 7일, 실제 값은 11월 8일”처럼 어느 부분이 왜 거절됐는지 남긴다. 다음은 설명용 가상 예시이며 앞선 실패 두 건의 원인이 아니다.

```text
입력 조건: 행사 시작일 2026-11-07
실패 초안: 세 번째 단계 EVENT_DAY 시작 2026-11-08T09:00:00+09:00
  → validate_plan: 행사 당일 시작일 불일치
  → 내부 진단: rule=event_start_mismatch, path=/steps/2/starts_at
               expected=2026-11-07, actual의 한국 날짜=2026-11-08
  → 진단 도구: 검증에 필요한 입력 + 실패한 PlanComposition + 위반 정보를 저장
  → 재검사 도구: 같은 저장본을 validate_plan에 다시 넣음 (모델 호출 0회)
  → 같은 규칙·위치·값으로 거절되는지 확인
```

AI에게 다시 써 달라고 해서 새 답이 잘 나오는지 확인하는 일이 아니다. 실패한 **같은 답안**을 다시 검사하는 것이다. 이 자료를 보고 모델이 조건을 어겼는지, 검증 코드가 잘못 막았는지를 요구사항과 대조해 판단한다.

1단계에서 `generation/validation.py`의 `PlanValidationViolation`과 내부 `PlanValidationError`를 구현했다. 실제 검사는 계속 `validate_plan()`의 같은 순서로 실행한다. 행사 당일 분기는 다음과 같다.

```python
if start and start != conditions.start_date:
    invalid('event_start_mismatch', path + '/starts_at',
            date_text(conditions.start_date), moment_details(step.starts_at), **location)
```

`invalid()`가 위반 객체를 담은 `PlanValidationError`를 올리면 기존 `AIInvalidResponseError` 처리에서 같은 공개 실패 안내로 바꾼다. 위 예시를 실제 검증기에 넣으면 `expected="2026-11-07"`, `actual={"timestamp":"2026-11-08T09:00:00+09:00","local_date":"2026-11-08"}`가 내부 오류에 남는다. UTC 11월 6일 16시는 한국 11월 7일이므로 정상 통과하는 경계도 검사했다.

2단계에서 `scripts/planning_validation_diagnostics.py`의 수집기와 `replay_planning_validation.py`를 구현했다. 흐름은 다음과 같다.

```text
validate_plan → PlanValidationError
  → capture_validation_failures: 입력/초안/위반 복사 → 같은 예외를 다시 올림
  → 기존 생성 Graph: generation_result.failed → Agent의 기존 설명/재시도
요청 종료 → failure-001.json 저장
replay_file → 저장 타입/해시 검사 → validate_plan만 실행 → 같은 위반인지 기록
```

재검사의 핵심은 아래 코드다. 생성 모델을 부르는 경로가 없다.

```python
graph.validate_plan(dict(
    request=snapshot.input.model_copy(deep=True),
    composition=snapshot.composition.model_copy(deep=True),
))
```

합성 11월 7일/8일 예시는 실제 저장 후 키·주소·모델을 비운 별도 프로세스에서도 `status=rejected`, `reproduced=true`, `same_validator_source=true`로 재검사됐다. [실패 자료](evaluation-results/planning-validation-details-2026-11-03/offline/example-failure.json)와 [재검사 결과](evaluation-results/planning-validation-details-2026-11-03/offline/example-replay.json)는 연습용이며 실제 모델 실패로 세지 않는다.

공개 결과의 failed/안내 문구와 검증 통과 기준은 유지하며, [11개 규칙·보관 항목·완료 기준](step-05-generation.md#11-실패한-초안과-구체적-검증-위반을-확보하기-239)을 따른다.

3단계에서는 최신 v7에서 같은 인원 변경 채팅 상태를 최대 10요청 실행했다. 수집기의 실제 중단 분기는 다음과 같다(기록 처리는 생략).

```python
for number in range(1, max_attempts + 1):
    # check.attempt()로 공개 P1 요청과 그 안의 재시도를 끝까지 실행한다.
    ...
    if files:
        report['status'] = 'captured' if all(replays) else 'replay_mismatch'
        break
else:
    report['status'] = 'limit_reached'
```

실제 10요청은 모두 성공해 파일을 보관할 검증 실패가 없었고, for의 `else`로 종료됐다. 요청을 다시 보낼 때마다 원래 JSON을 복원하며 앞 요청의 성공 초안을 재사용하지 않는다. 이 실험 상한은 제품의 자동 재시도 횟수를 바꾸지 않는다. [실제 원본과 검산](evaluation-results/planning-validation-details-2026-11-03/real-v7/analysis.json)을 보존했고, 기존 v6 실패를 대체하거나 진단 기능의 개선 효과로 해석하지 않았다. 다음에 실패가 나오면 저장본의 같은 규칙/위치/값을 재검사할 수 있는 상태다.

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

[AgentPlanPreview.tsx](../../tests/ui/planning/src/features/planning/components/AgentPlanPreview.tsx)가 검증된 preview를 테스트 앱 안의 StepFlow에 전달한다. [generation-playground.ts](../../tests/ui/planning/src/features/planning/generation-playground.ts)의 `toPreviewSteps()`는 서버 이름·묶음·담당·목적·예정 행동을 표시 타입으로 바꾼다. 미정 날짜는 '미정'이다. 수정 콜백을 전달하지 않아 수정 버튼도 보이지 않는다. 제외 단계도 서버 응답의 name과 reason을 그대로 표시한다. 이름 조회를 위한 FE/BE 코드 변환표는 제거했다(#198).

버튼 활성화는 행사 유형과 일정·인원·장소의 답변 여부 및 미해결 변경을 확인한다. 권유 상태가 deferred여도 사용자가 직접 누르면 요청할 수 있다. 전송 중에는 입력·초기화·다음 버튼을 잠그고, 버튼 요청에는 별도 생성 중 화면을 표시한다. 단계별 진행률을 알 수 없는 상태에서 가짜 퍼센트는 표시하지 않는다.

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

## 생성 보류가 날짜 질문 보류로 번지지 않게 하기 (#205)

사용자가 “예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마.”라고 말하면 현재 지침은 다음 두 행동을 구분한다.

```text
agent: 현재 상태와 이번 발화 해석
  → update_event_conditions(changes=[인원 60명], defer_topics=[], resume_topics=[])
  → update_generation_offer(action=defer, 근거="계획 초안은 만들지 마.")
  → 인원 변경과 생성 보류 설명
결과: 인원만 60명, 날짜 질문 보류는 추가하지 않음
```

날짜가 미정이라는 사실은 날짜 질문을 보류하라는 사용자 의사와 다르다. “날짜와 장소는 나중에 정할게. 초안도 만들지 마.”라면 주제 보류와 생성 권유 보류를 각각 처리한다. 이 구분은 planning-agent-v7에서 넣었다(현재는 메시지 순서만 바꾼 v8, #269). 생성 후 설명은 실제 단계와 행동을 따르고, 수동 단계만으로 담당자 입력 UI나 자동 후속 처리가 생겼다고 말하지 않는다. `prompts/chat.md`의 구분을 명시했으며 Tool 스키마, 조건 변경 처리기와 Node 연결은 바꾸지 않았다. 원문 존재 검사가 의미 연결까지 보장하지 않는 기존 한계도 유지한다.

검증 도구 [check_planning_deferrals.py](../../scripts/check_planning_deferrals.py)는 같은 공개 함수와 상태에서 기존/수정 시스템 지침만 교체해 한 요청씩 번갈아 실행한다. 인원, 나머지 조건, 보류 목록과 생성 보류를 확인하고 tentative/specified 차이는 점수 대신 진단으로 남긴다. 날짜 보류와 재개를 실제로 요청한 사례도 함께 검사해 모든 주제 변경을 막는 방식이 통과하지 못하도록 했다. 기존 #196 점수는 별도로 유지한다. 실제 모델의 개선 여부는 [평가 기록](evaluation.md)에 확인한 결과만 남긴다.

실제 비교에서 핵심 입력의 불필요한 날짜 보류는 기존 지침 17/30건, 수정 지침 0/30건이었다. 날짜를 직접 보류하거나 “그건 나중에”로 날짜 질문을 가리킨 사례도 각각 3/3건 처리했다. 다만 “날짜는 다시 얘기하자”를 나중에 논의하자는 뜻으로 해석한 실패 1건을 남겼고, 이후 명확한 재개 표현은 별도 3/3건 통과했다. [102요청 원본과 해석](evaluation-results/planning-deferrals-2026-10-29/README.md)을 함께 본다.

이번 수정은 요청 해석 지침의 경계를 보완한 것이다. Tool의 원문 존재 검사만으로 모든 의미 오류를 막는다고 설명하지 않는다. 이미 저장된 dates 보류를 사용자 의사 확인 없이 삭제하지도 않는다. 실제 날짜 보류였을 수 있으므로 보류 재개 요청과 구분해야 한다.

## 대화 모델에 보내는 메시지 순서 (#269)

대화 모델(`agent_node`)은 매 호출 지시문, 대화 이력, 이번 발화, 이번 턴의 Tool 결과와 함께 **실행 문맥**을 받는다. 실행 문맥은 코드가 만든 현재 상태 JSON이다(이번 메시지 ID, 기준일, 현재 초안, 검색·생성 가능 여부, 생성 권유 상태). 순서는 `nodes.agent_messages()`가 정한다.

```text
입력: "예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마." (메시지 ID u2)

agent_node
  → context = {"current_message_id": "u2", "draft": {"headcount": 50, …}, "generation": {…}, …}
  → agent_messages(context, state["messages"], allow_tools=True)

호출 1  [시스템: chat.md] [이력…] [사용자: 60명…] [시스템: 실행 문맥 headcount=50]
        → update_event_conditions(인원 60명)
호출 2  [시스템: chat.md] [이력…] [사용자: 60명…] [Tool 요청·결과] [시스템: 실행 문맥 headcount=60]
        → update_generation_offer(action=defer)
호출 3  [시스템: chat.md] [이력…] [사용자: 60명…] [Tool 요청·결과 ×2] [시스템: 실행 문맥 generation=deferred]
        → 답변
```

맨 앞 시스템 메시지는 지시문 원문뿐이라 모든 호출에서 글자 그대로 같다. 바뀌는 실행 문맥은 맨 끝에만 있다. 이 공급자는 첫 시스템 메시지가 조금이라도 다르면 입력 캐시를 쓰지 않았기 때문이다. v7은 지시문 뒤에 실행 문맥을 붙여 첫 시스템 메시지 하나로 보냈고, 메시지 ID가 매 요청 달라 대화 호출 캐시가 항상 0이었다. Tool 한도에 도달한 호출은 마지막 실행 문맥 끝에 "이번 턴의 Tool 한도에 도달했습니다…"(`TOOL_LIMIT_NOTICE`)를 붙이고 Tool을 끈다.

실행 문맥 메시지는 모델 호출에만 붙이고 `state["messages"]`에는 저장하지 않는다. 그래서 다음 턴의 이력이나 생성 입력(`plan_messages`)에 들어가지 않는다.

테스트 `test_first_system_message_is_identical_across_turns_and_calls_for_provider_cache`가 서로 다른 턴·호출의 첫 시스템 메시지가 같고, 같은 턴 2번째 호출이 1번째 호출의 실행 문맥만 빼고 앞부분을 그대로 이어 쓰는지 고정한다. v7과 v8은 [compare_agent_context_layout.py](../../scripts/compare_agent_context_layout.py)로 같은 실행 안에서 번갈아 쟀다. 요청마다 `agent_messages`를 v7 함수로 바꿔 끼우고 끝나면 되돌린다. 결과는 [11-04 측정 기록](evaluation-results/planning-agent-context-layout-2026-11-04/README.md)에 있다.

## 생성 모델은 얼마나 생각하고 쓰나 (#264)

생성 모델은 계획 JSON을 쓰기 전에 내부에서 추론한다. 추론에 쓴 토큰도 출력 토큰에 들어가고, 생성 호출 시간은 출력 토큰 수에 거의 비례한다(#263). 그래서 추론 깊이(reasoning effort)를 `low`로 정해 둔다.

```text
입력: 「다음: 흐름 만들기」 클릭 (MT / 50명 / 날짜·장소 미정)

generate_planning_preview
  → run_plan_generation → compose_plan
      → invoke_plan_composition
          → build_plan_model()   max_tokens=8192, streaming=True, reasoning={"effort": "low"}
          → ainvoke_structured(..., PlanComposition)
  → validate_plan → 13단계 초안

같은 입력을 30번씩 번갈아 잰 값(11-04)
  추론 미지정  출력 약 1,500토큰(그중 추론 516) → 생성 호출 p50 15.4초
  low         출력 약 1,190토큰(그중 추론 240) → 생성 호출 p50 11.1초
```

추론을 뺀 계획 JSON은 두 설정 모두 약 930~950토큰이었다. 단계 수(13)와 계획 검증 통과도 줄지 않았다. 값은 `generation/model.py`의 `PLAN_REASONING` 한 곳에 있고, 테스트 `test_default_graph_uses_streaming_budget_and_validates_complete_preview`가 실제 SDK 요청 본문에 `reasoning: {"effort": "low"}`가 실리는지 고정한다.

비교는 [compare_generation_reasoning.py](../../scripts/compare_generation_reasoning.py)로 했다. 요청마다 `build_plan_model`을 변형 함수로 바꿔 끼워 `reasoning`만 덮어쓰고(기본값 변형은 `None`이라 값을 보내지 않음), 끝나면 되돌린다. 계획 검증에서 거절되면 #239의 `capture_validation_failures`로 어느 규칙에서 거절됐는지 남긴다. 결과는 [추론 깊이 측정](evaluation-results/planning-generation-reasoning-2026-11-04/README.md)에 있다.

## 한 응답에 Tool이 여러 개 오면 (#265, #274)

대화 모델은 Tool 요청을 응답에 적어 보내고, 코드가 실행한 결과는 그다음 호출에서야 받는다. 지금은 한 응답에 Tool을 여러 개 받는다(`llm.ainvoke_with_tools`의 `parallel_tool_calls`, 행사계획은 `nodes.PARALLEL_TOOL_CALLS = True`).

```text
"예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마."

하나만 허용     호출 1 update_event_conditions(인원 60) → 결과
               호출 2 update_generation_offer(defer)   → 결과
               호출 3 답변
지금 (여러 개)  호출 1 update_event_conditions(인원 60) + update_generation_offer(defer)
                      → tools_node가 앞에서부터 차례로 실행
               호출 2 답변
```

여러 개 허용은 11-04에 쟀다. 호출이 3번에서 2번, 요청 p50이 7.19초에서 6.17초로 줄었다(#265). 처음에는 "날짜는 다시 얘기하자. …"의 통과가 줄어 보류했는데, 실패한 응답의 Tool 인자를 보니 두 설정 모두 "나중에 다시 얘기하자"로 읽어 날짜를 다시 보류한 같은 모양이었다. 분명한 재개("이제 날짜 정하자")와 정정("아니, 날짜는 지금 정하자는 거였어")은 두 설정 모두 10/10이라 켰다(#274, [평가 기록](evaluation.md)).

모델이 여러 개를 보내면 `tools_node()`가 아래를 지킨다. 같은 응답 안의 뒤 Tool은 앞 Tool의 결과를 보지 못한 채 인자가 정해졌기 때문이다.

```text
"작년 봄 MT 참가비로 하자" → [search_past_events, update_event_conditions(참가비 30,000원)]
  search_past_events  → 실행. 결과 "작년 봄 MT 참가비 45,000원"
  update_event_conditions → 실행하지 않음(rejected). "검색 결과를 확인한 뒤 다시 요청"
  다음 호출에서 모델이 45,000원을 보고 다시 변경

"60명으로 바꿔줘. 초안은 만들지 마." → [update_generation_offer(defer), update_event_conditions(인원 60)]
  보류 → 50명 기준으로 저장
  인원 변경 성공 → 이번 응답에서 남긴 보류의 기준을 60명 초안으로 맞춤
  (맞추지 않으면 다음 턴에 "조건이 바뀌었다"며 같은 권유를 다시 할 수 있다)
```

`tools_node()` 안에서는 `searched`(앞에 검색이 있었나)와 `deferred_offer_id`(이번 응답에서 남긴 보류)로 이 둘을 판단한다. 사용자가 값을 직접 말한 변경은 보통 [변경, 검색] 순서로 오므로 그대로 실행한다. 고정 응답 회귀 테스트는 [test_planning_agent_parallel_tools.py](../../tests/test_planning_agent_parallel_tools.py)에 있다. 비교 실행기는 [compare_parallel_tool_calls.py](../../scripts/compare_parallel_tool_calls.py)이고 요청마다 `PARALLEL_TOOL_CALLS`만 바꿔 끼운다.

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

일반 상담과 인원 변경도 별도 사례로 둔다. 한 번 잰 숫자 대신 같은 입력으로 반복하고, 실패를 빼고 성공률을 계산하지 않는다. 상세 사례, 반복 횟수와 통계 규칙은 [응답 시간 기준 측정](latency-baseline.md)에 있다. 고정 입력, 반복 실행기, 전체/세부 구간 관측과 기록의 p50/p95 집계를 구현하고 실제 모델 3세션의 본측정 120건을 수집했다. 아래의 고정 시계 설명과 끝부분의 실제 요청 예시를 구분한다.

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

[planning_latency_inputs.py](../../scripts/planning_latency_inputs.py)의 `make_request()`는 매번 고정 JSON에서 state를 복원한다. request_id와 이번 message_id만 고유하게 만들고 날짜·장소 명시 보류, 조건, 이력과 권유는 유지한다. 과거 실측과 입력이 달라 직접 비교하지 않는다. G2라면 message가 없는 `PlanningPreviewRequest`를 만든다. 기존 성공 초안을 재사용하지 않으므로 같은 생성 경로를 다시 실행할 수 있다.

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

### 예시: 기록한 숫자가 올바른 요약으로 나오는지 확인한다

아래는 계산 검증용 숫자다. 실제 모델의 응답 시간이 아니다.

```text
한 사례의 본 측정 6회
  성공: 2초, 3초, 4초, 5초, 6초
  실패: 90초 뒤 timeout
준비 실행 1회: 별도 보관

load_session(): 시작과 종료 연결, 해시와 순서 확인
  → 본 측정과 준비 실행 분리
  → 성공 5개와 실패 1개 분리
  → summarize_group()
      성공률 = 5 / 6
      성공 p50 = 4초, p95 = 5.8초
      실패 시간 = 90초
```

[summarize_planning_latency.py](../../scripts/summarize_planning_latency.py)의 `load_session()`은 고정 입력과 실제 요청이 같은지, 시작/종료가 짝을 이루는지 확인한다. 중복 기록이 있으면 같은 요청을 두 번 세게 되므로 계산하지 않고 거절한다. 시작만 남았다면 pending으로 보관하고 부분 요약을 만든다. API 설정과 모델은 사용하지 않는다.

[planning_latency_summary.py](../../scripts/planning_latency_summary.py)의 핵심은 시간 표본과 성공률의 분모를 구분하는 것이다.

```python
successful = [item for item in finished if item['outcome'] == 'success']
success_rate = len(successful) / len(started) if started else None
success_ms = distribution(item['ai_request_ms'] for item in successful)
```

실패는 성공 시간의 분위수에 섞지 않지만 성공률의 분모에는 남는다. 종료가 없는 요청도 시작 수에는 포함하고, 지연 표본에는 0ms를 넣지 않는다. 시작 자체가 없으면 성공률은 null이다.

`distribution()`은 정렬한 성공 표본의 95% 위치를 구하고 양옆 값을 선형 보간한다. 위 예시에서는 5초와 6초 사이를 계산해 5.8초가 나온다. NumPy의 기본 linear/R7과 같은 계산이며 새로운 의존성은 추가하지 않았다. 표본이 하나라면 그 한 값, 없으면 null로 표시하며 작은 표본을 서비스 보장으로 해석하지 않는다.

`aggregate_sessions()`는 같은 입력, 모델 설정과 코드인 세션만 합친다. 각 세션의 p95를 평균 내지 않고 원본 성공 시간을 한곳에 모아 `distribution()`을 다시 호출한다. 세션별 요약도 따로 남긴다.

결과는 별도 JSON과 콘솔 표다. `groups.measurement.C1.success_ms.p95_ms`처럼 본 측정의 사례와 지표를 찾아볼 수 있고, 준비 실행은 `groups.warmup`에서 확인한다. 기록이 완전해도 실패 요청은 있을 수 있으므로 complete와 성공률을 따로 본다. [집계 명령과 필드 안내](latency-baseline.md#모델-없이-저장-결과-집계), [고정 데이터 검증 결과](evaluation.md#고정-응답으로-기록과-집계-검증-2026-10-28)를 참고한다.

### 세부 구간은 어느 함수의 앞뒤에서 재는가

사용자가 생성 권유에 “응, 만들어줘.”라고 답한 요청을 보자. 아래 시간은 흐름을 검증하기 위해 가상 시계에 직접 넣은 값이다. 실제 모델 속도가 아니다.

```text
PlanningChatRequest(같은 MT 조건과 pending offer, message="응, 만들어줘.")
  → measure_attempt(): 요청 시계 시작
    → chat_planning()
      → call_agent_model(): 생성 Tool 선택 응답                    0~10ms
      → generate_event_plan Tool
        → run_plan_generation(): 생성 Graph 전체                10~42ms
          → compose_plan(): 입력 구성과 초안 작성               10~40ms
            → invoke(..., PlanComposition): 생성 모델 호출       10~40ms
          → validate_plan(): 코드로 계획 검증                   40~42ms
      → call_agent_model(): 결과 설명 응답                       42~47ms
    ← 공개 결과와 next_state 반환
  → 요청 시계 종료: 47ms
  → 결과 검사와 파일 저장: 시간 집계에서 제외
```

첫 모델 응답은 생성 Tool을 고르고, 그 Tool이 초안 생성 Graph를 실행한다. 모델이 구조화 초안 `PlanComposition`을 쓰면 코드가 카탈로그/날짜/행동/근거를 검사해 `EventPlanPreview`로 바꾼다. 마지막 대화 모델은 이 결과를 읽어 사용자에게 설명한다. 관측기는 이 기능들을 호출하는 순서를 바꾸지 않는다.

측정 도구 안의 [install_observers()](../../scripts/planning_latency_observation.py)는 기존 함수에 잠시 래퍼를 붙인다. `public_workflow.run_plan_generation`, `agent.graph.call_agent_model`, `generation.graph.compose_plan/validate_plan`을 감싼다. 실행이 끝나면 `ExitStack`이 원래 함수로 복원한다. 함수 정의 때 이미 기본 인자로 묶인 생성 모델도 놓치지 않도록, compose에 실제 전달된 invoke를 다시 감싼다.

```python
# wrap_async(): 기존 함수를 실제로 호출하는 앞뒤가 하나의 구간이다.
with trace.span(stage, **details) as item:
    result = await function(*args, **kwargs)
```

`RequestTrace.span()`은 진입 때 `perf_counter_ns()`를 읽고, 반환/예외/취소 모두 finally에서 종료 시계를 읽는다. 모델의 성공 응답을 받은 뒤가 아니라 진입 기록을 만들 때 논리 호출 시도가 생긴다. 따라서 첫 대화 모델이 timeout으로 끝나도 시도는 1회다. SDK 안에서 HTTP를 여러 번 재시도했는지는 별도로 관측하지 않으므로 추정하지 않는다.

각 요청은 `capture_request()`의 ContextVar를 가진다. 위 요청의 기록은 다음과 같이 묶인다.

| ID | 구간 | 부모 ID | 관측 시간 |
| --- | --- | --- | --- |
| 1 | agent_model | 없음 | 10ms |
| 2 | generation | 없음 | 32ms |
| 3 | compose_plan | 2 | 30ms |
| 4 | generation_model | 3 | 30ms |
| 5 | validate_plan | 2 | 2ms |
| 6 | agent_model | 없음 | 5ms |

**generation 32ms 안에 compose 30ms와 validate 2ms가 들어 있다. compose 30ms 안에는 generation_model 30ms가 포함된다.** 그러므로 전체를 `10 + 32 + 30 + 30 + 2 + 5`로 더하면 안 된다. 이 가상 시계에서는 기타 작업 시간을 0으로 두어 전체가 `10 + 32 + 5 = 47ms`다. 실제로는 상태 변환, 프롬프트 준비, Graph 스케줄링과 관측 오버헤드가 있어 전체 시간이 더 클 수 있다. 남는 시간을 순수 모델 시간이라고 부르지 않는다.

동일 조건에서 버튼으로 요청하면 대화 Agent를 거치지 않는다. `generate_planning_preview()` → 공통 생성 Graph만 실행하므로 위 시계에서는 32ms이며 논리 모델 시도는 대화 0회, 생성 1회다. 채팅은 대화 2회, 생성 1회다.

### 저장된 구간과 집계는 어떻게 읽는가

요청이 끝나면 `measure_attempt()`가 시계를 멈추고 observation 스냅샷을 만든다. 다음은 위 생성 모델 구간의 일부다.

```json
{
  "id": 4,
  "parent_id": 3,
  "stage": "generation_model",
  "start_ms": 10,
  "end_ms": 40,
  "duration_ms": 30,
  "outcome": "ok"
}
```

새 `report_version=2`의 finished 이벤트에는 `observation.spans`와 `model_call_attempts`가 들어간다. 메시지 본문이나 공급자 예외 원문은 구간에 복사하지 않는다. 모델 메시지 text 길이와 개수는 숫자로 남기지만 Tool 스키마를 포함한 전체 입력 토큰 수는 아니다. 전체 입력·출력 토큰은 #263부터 모델 구간의 `usage`(입력, 출력, 그중 추론, 캐시 입력)에 따로 남는다. 측정 세션에만 등록한 LangChain 콜백이 모델 호출이 끝날 때 열린 구간에 붙이며, 못 받은 경우는 0이 아니라 `usage_missing`에 이유를 남긴다([토큰 사용량 관측](latency-baseline.md#토큰-사용량-관측의-구현-범위)).

집계기는 시간이 부모/요청 범위 안에 있는지, 자식과 부모의 유형이 맞는지, 호출 수가 실제 구간 수와 일치하는지 확인한다. 그런 뒤 `groups.measurement.G1.observation`에 구간별 요약을 붙인다.

- `model_call_attempts`: 위 요청에서는 agent_model=2, generation_model=1이다.
- `by_stage.agent_model.per_call_ms`: 호출 시간 10ms와 5ms, 표본 2개다.
- `by_stage.agent_model.per_completed_request_total_ms`: 한 요청의 대화 모델 합계 15ms, 표본 1개다.
- `by_stage.generation.per_call_ms`: 전체 생성 함수의 32ms다. 자식 시간을 다시 합하지 않는다.

버튼의 대화 모델은 calls=0이다. 단일 호출 표본이 없으므로 per_call_ms의 p95는 null이고, 그 요청의 대화 모델 총합은 0ms다. 반면 옛 version=1은 관측 자체가 없으므로 observation이 null이다. 서로 다른 형식은 합쳐 측정한 것처럼 집계하지 않는다.

### 실패하거나 다시 시도하면 어떻게 남는가

생성 모델이 timeout을 내면 그 구간의 오류 타입과 timeout 분류를 먼저 남긴다. 생성 Graph가 이를 안전한 `PlanGenerationResult(status="failed")`로 바꿔 정상 반환해도, 기록기는 이미 관측한 원인을 연결해 `failure.stage=generation_model`로 기록한다. 계획 코드 검증이 실패했다면 stage=validate_plan, category=invalid_plan이다. 공개 실패 문구를 분석해 추측하지 않는다.

Agent가 그 실패 뒤 생성 Tool을 다시 선택해 성공하면 최종 요청은 성공일 수 있다. 그래도 첫 실패 구간과 두 번째 성공 구간 모두 남는다. 검증 사례에서는 생성 함수 30ms 실패와 32ms 성공을 보존해 요청당 생성 합계 62ms, 생성 모델 논리 시도 2회를 확인했다. 이는 원래 Agent의 선택을 관측한 것으로 새 재시도 정책을 넣은 것이 아니다.

취소한 모델 호출은 관측한 대기를 interrupted_wait_ms로 남기고 완료 시간과 분리한다. 동기 검증 함수가 스레드에서 계속 실행 중이라면 end_ms와 duration_ms는 null, outcome은 running으로 남긴다. 뒤늦게 끝나도 이미 종료한 요청의 스냅샷에 시간을 섞지 않는다. 구간 집계는 pending_calls로 표시하고 해당 시간을 분위수에서 제외한다. [측정 범위와 형식 안내](latency-baseline.md#세부-구간-관측의-구현-범위), [검증 결과](evaluation.md#세부-구간과-논리-모델-호출-관측-검증-2026-10-28)를 함께 참고한다.

### 실제 모델에서는 어떤 시간이 기록됐는가

2026-10-28에 `be76b60`의 기존 모델/프롬프트/재시도 설정으로 준비 실행 12건과 본측정 120건을 실행했다. 앞부분의 47ms 예시는 검산용 가상 시간이고, 여기부터는 `gpt-5.6-luna` 실제 응답 시간이다. [모든 결과와 재집계 방법](evaluation-results/planning-latency-real-2026-10-28/README.md)을 보존했다.

먼저 사용자 입장에서 다음 입력을 보자.

```text
현재 상태: MT, 50명, 참가비 25,000원, 날짜와 장소 미정
직전 Agent: 이 조건으로 준비 순서 초안을 만들까요?
사용자: “응, 만들어줘.”
```

성공 요청의 p50에 가까운 실제 요청 `real-20261028-01-measurement-0004-G1`을 따라가면 다음과 같다. 한 요청의 실제 값이며 전체 요청의 평균은 아니다.

```text
make_request(G1)
  → 같은 fixture 복원, 이번 message와 고유 request_id 준비 (측정 전)
measure_attempt()
  → 타이머 시작
    → chat_planning(request)
      → call_agent_model()                       1.929초
        “응”을 pending offer 수락으로 해석, generate_event_plan 선택
      → generate_event_plan Tool
        → run_plan_generation()                 12.078초
          → compose_plan()                      12.075초
            → 생성 모델, PlanComposition 반환   12.074초
          → validate_plan()                      0.239ms
            카탈로그/날짜/행동/근거 검사 → EventPlanPreview
      → call_agent_model()                       2.973초
        검증된 초안을 보고 설명 답변 작성
    ← PlanningPublicResult(view, next_state)
  → 타이머 종료: 전체 16.988초
  → inspect_result() → JSONL finished 기록 (측정 후)
```

여기서 생성 12.078초 안에 작성/생성 모델/검증 시간이 들어 있다. 전체는 대략 `대화 1.929 + 생성 12.078 + 대화 2.973 + 기타 처리`다. 검증 0.239ms는 초 단위가 아니다. 부모와 자식을 모두 합하거나 모델 시간을 공급자 순수 추론 시간으로 읽지 않는다.

코드가 반환한 핵심 결과는 다음과 같다.

```text
view.generation_result.status = generated
view.generation_result.preview.steps = 13개
next_state.payload.generation.preview = 같은 검증된 preview
view.draft.conditions.headcount = 50 (입력 조건 유지)
단계 날짜와 행동 기한 = null (행사 날짜 미정 유지)
```

답변은 “현재 조건으로 MT 준비 순서 초안을 만들었어요”로 시작하고 날짜/장소 미정을 설명했다. UI의 단계 데이터는 답변 문자열을 파싱하지 않고 구조화 preview를 사용한다. 이 답변은 정산과 환급을 한 항목으로 요약해 12개 항목으로 표현했지만 실제 구조화 단계는 13개였다. 자동 통과를 모든 설명 문구에 대한 품질 보장으로 읽으면 안 된다.

버튼은 같은 생성 Graph로 바로 진입한다. 실제 요청 `real-20261028-02-measurement-0002-G2`에서는 다음과 같이 기록됐다.

```text
generate_planning_preview(request)
  → run_plan_generation() 11.827초
    → 생성 모델 11.822초, validate_plan 0.249ms (부모 시간에 포함)
  ← 전체 11.828초, 12단계 preview, reply=None
대화 모델 0회, 생성 모델 1회, 대화 이력 유지
```

두 요청 모두 공통 생성 Graph를 사용하지만 같은 결과를 재사용한 것은 아니다. 실제 생성 결과도 13단계와 12단계로 달랐다. 두 사례의 성공 p50은 각각 17.066초와 11.828초였다. 생성 입력과 출력도 다르므로 그 차이를 전부 대화 모델 비용이라고 단정하지 않는다.

### 응답이 왔다는 것과 원하는 결과가 나왔다는 것

검사 코드는 [inspect_result()](../../scripts/planning_latency_checks.py)다. 모델을 추가로 호출하지 않고 반환된 조건과 상태를 비교한다.

```python
# C2: 입력 조건 사전을 복사한 뒤 headcount만 60으로 기대한다.
expected = request.draft.conditions.model_dump()
expected['headcount'] = 60
conditions_match = view.draft.conditions.model_dump() == expected
# 실제 검사는 지정 상태(specified), 다른 metadata와 deferred_topics 유지도 따로 확인한다.
```

C2는 30건 모두 headcount를 60으로 바꿨다. 그런데 19건에서 사용자가 요청하지 않은 `deferred_topics=[dates]`가 생겼고, 4건에서 인원을 지정값 대신 잠정값(tentative)으로 적었다. 1건이 중복돼 엄격한 검사를 모두 통과한 요청은 8건이었다. “예상 참가 인원”이라는 표현에 잠정 해석 여지가 있으므로 먼저 기대 상태를 확인한다. 이 불일치를 “인원 값을 못 바꿨다”라고 요약하면 실제 문제가 가려진다.

G1/G2의 최종 실패 5건은 모델 응답은 왔지만 `validate_plan()`이 거절한 경우다. 현재 공개 실패 결과는 실패 사유를 묶어 반환하고 관측기도 `invalid_plan`까지만 기록한다. 어떤 세부 규칙이었는지는 이 원본만으로 확정할 수 없다.

실제 G1 요청 `real-20261028-02-measurement-0003-G1`은 다음 경로였다.

```text
Agent → 생성(12.080초) → 코드 검증 실패
      → Agent → 생성 재시도(12.175초) → 코드 검증 다시 실패
      → Agent 설명 → generation_result.status=failed
전체 31.244초, 대화 모델 3회, 생성 모델 2회
```

따라서 관측기를 통해 “시간은 생성 모델 대기에 주로 쓰였고, 거절된 초안을 다시 생성해 더 기다린 요청이 있다”까지 확인했다. 코드 검증 실행은 생성 시도 61회의 평균 약 0.216ms여서 그 연산 자체를 먼저 최적화할 근거는 없다. 다음은 C2 기대 상태와 부가 변경 확인, 계획 검증의 안전한 세부 원인 관측이다. 그 뒤 같은 프로필로 변경 전후를 비교한다. 실제 제품 HTTP/DB/FE 대기 시간과 SDK 내부 HTTP/토큰은 이번 측정 범위 밖이다.

## 대화가 길어졌을 때 안내하는 흐름 (#194)

예를 들어 저장 이력 44개에서 “인원은 50명으로 잡자”를 처리한다고 하자.

```text
44개 + 사용자 발화 1개
     + AI의 조건 Tool 요청 1개
     + Tool 결과 1개
     + AI 최종 답변 1개
  → capture_turn_state(): 48개 이력을 JSON 상태로 구성
  → build_result(): 저장할 이력 수를 계산
  → view.history_usage = {message_count: 48, max_messages: 60, near_limit: true}
  → BE 저장/전달 → FE 안내 표시 [제품 연결 필요]
```

핵심은 LLM이 사용량을 추측하지 않는 것이다.

```python
# public_workflow.build_result() 안에서 두 요청 경로가 같은 기준을 사용한다.
history_usage = PlanningHistoryUsage.from_count(len(state.payload.history))
# 반환할 view에 붙이고, next_state 자체는 그대로 보존한다.
```

`PlanningHistoryUsage`는 루트 `contracts.py`에 있다. `from_count()`가 사용량과 한도 임박을 계산하고 계약 검증이 범위와 일관성을 확인한다. 안내는 48개부터이며 다음 대화를 몇 번 할 수 있다는 뜻은 아니다. 61개 이상이면 기존 상태 캡처가 오류를 내므로 중간값을 정상 결과로 반환하지 않는다.

이후 버튼으로 생성해도 새 채팅 이력이 없으므로 48개를 유지한다. JSON 저장 후 복원한 상태를 다시 사용해도 같은 개수다. 과거 화면 응답에 필드가 없으면 null이며 0개로 꾸미지 않는다. Agent 상태 형식 버전은 바꾸지 않는다.

독립 UI의 테스트 API도 같은 `from_count()`를 사용하고 화면은 `near_limit`만 읽어 안내를 표시한다. 프롬프트와 Tool은 바꾸지 않는다. 제품 HTTP 매핑은 [공개 계약 14절](p1-public-contract.md#14-대화-이력-안내-194)의 AI 구현안이며 BE/FE 합의와 실제 연결은 남아 있다.

## 수정 → 검토: P2 계획 수정 후 AI 검토 (#177)

생성된 계획에서 운영진이 "수요 조사"를 빼고 「단계 수정」에서 저장하면 검토가 자동으로 이어지는 예시다(카드에는 「검토 받기」·「다시 시도」·「다시 검토」 버튼이 있다). 인원은 "대략 30명"으로 잠정이다. 평가 케이스 `survey_removed`와 같은 입력이다.

```text
FE: 「단계 수정」 저장(PATCH /plan/steps) → 저장 뒤 GET /plan/steps/snapshot의 planRevision이
    편집을 시작할 때 본 값보다 커졌을 때만 → POST /api/v1/events/{id}/plan/review {expectedRevision}
  → plan_review_service.request_review()
     · 행사·검토 행을 잠그고 버전 확인(다르면 409), 같은 버전을 이미 끝냈으면 AI를 다시 부르지 않음
     · build_review_request(draft, today, current, baseline, ai_excluded)
         baseline(생성 직후 스냅샷)과 current를 비교해 changes를 채움
     · REVIEWING으로 커밋한 뒤 잠금을 놓고 AI 호출
  → app.ai.review_plan_edit(request)
  → 결과를 요청이 아직 최신일 때만 저장(DONE/FAILED) → 카드 표시
```

`build_review_request()`가 만드는 입력의 핵심은 아래와 같다. DB 접근이 없는 순수 함수다.

```python
PlanEditReviewRequest(
    draft=...,  # headcount=30은 condition_meta에서 tentative
    included_steps=(ReviewStep(code=RECRUIT_NOTICE, ...), ...),
    excluded_steps=(ReviewExcludedStep(code=DEMAND_SURVEY, excluded_by="user"),),
    changes=PlanChangeSet(removed_codes=(DEMAND_SURVEY,)),
)
```

`excluded_by`는 처음 생성 때 AI가 뺀 단계(`ai`)와 사용자가 뺀 단계(`user`)를 구분하려고 둔다. AI가 뺐던 단계를 사용자가 다시 넣으면 `added_codes`에 들어가고 제외 목록에서 사라진다.

`features/planning/review/review.py`의 `review_plan_edit()`는 프롬프트(`prompts/review.md`)를 시스템 메시지로, 요청 JSON을 별도 사용자 메시지로 보내 `PlanEditReviewResult`를 받는다. 요청 속 문장은 데이터로만 취급한다. 결과의 `step_codes`가 입력의 포함·제외 단계에 없으면 `AIInvalidResponseError`를 낸다. 모델이 입력에 없는 단계를 지어내면 화면에 잘못된 안내가 나가기 때문이다.

결과가 카드가 되는 모습은 이렇다.

```text
outcome=issues, items=[{step_codes:[DEMAND_SURVEY, CHECK_RESPONSES, CONFIRM_DETAILS, BOOK_VENUE], kind:missing_step,
  message:"수요 조사를 빼면, 약 25명이라는 잠정 인원을 행사 전에 별도로 확인하는 단계가 없어져요. …",
  suggestion:"모집 공지와 신청 현황 확인에서 잠정 인원을 검증한 뒤 …"}]
  → BE가 status=DONE, items 저장 → PlanReviewCard가 항목별로 message와 suggestion 표시
outcome=no_issues → "이번 검토에서는 추가로 짚을 주의점을 찾지 못했어요" 카드
AI 오류 → status=FAILED(error_code) → 카드가 실패와 다시 시도 표시, 편집은 그대로
```

위 결과 예시는 실제 모델 평가의 `undecided_dates`(날짜 미정, 인원 약 25명 잠정) 응답이며 입력 예시와 다른 케이스다. 입력 예시의 시나리오(`survey_removed`)는 평가에서 no_issues가 나왔다. 인원이 잠정이어도 수요 조사 누락을 짚지 않은 것으로, 남은 한계다. 고정 케이스 6개의 결과와 프롬프트 수정 전후는 [평가 기록](evaluation.md#계획-수정-검토-실제-모델-확인-177-ai-plan-07-2026-11-01)에 있다. 직접 돌리려면 api 컨테이너에서 `python -m app.ai.scripts.run_plan_review_eval --out <폴더>`를 실행한다. AI는 계획을 자동으로 고치지 않으며 검토한 버전(`reviewed_revision`)과 현재 버전이 다르면 FE가 최신 검토로 표시하지 않는다.
