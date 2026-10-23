# 행사계획 코드 따라가기 — 말에서 조건 변경을 추출하기

현재 범위: 작업 1~2 내부 구현. 질문 선택은 작업 3, 화면 응답 조립·저장은 후속 작업이다.

```text
기존 조건 + 이번 발화 + 이전 대화
  → ConditionExtractionInput 입력 검사
  → extract_condition_changes: 구조화 LLM 추출
  → validate_and_apply: 근거·타입·날짜 검증
  → 조건 후보 + 적용 변경 + 미해결 항목
```

실제 모델 검증과 한계는 [평가 기록](planning-evaluation.md)에 있다. 공개 plan_chat·DB 저장·LangGraph 전체는 아직 연결하지 않았다.

## LLM은 대화 전체에서 한 번만 호출하나?

사용자 발화 한 턴마다 `extract_condition_changes()`를 호출하고, 이 함수 안에서 구조화 추출을 한 번 요청한다. 사용자 발화가 세 번이면 추출 호출도 세 번이다. 네트워크 재시도는 공통 호출 설정에 따른 별도 전송일 수 있다.

매 턴 최신 조건·이번 발화·이전 대화 문맥을 전달한다. 모델은 이번 발화의 변경/모호함을 해석하며, 이미 정한 조건을 모두 다시 질문하는 방식은 아니다. 다음 턴의 최신 조건과 대화 이력을 공급하는 BE 연결은 아직 구현하지 않았다.

## 2. 먼저 알아둘 네 가지

**스냅샷(snapshot)**은 특정 시점의 조건 묶음이다. `headcount=32, location="가평"`처럼 지금 정해진 값을 담는다. `None`은 미정이고, 참가비 `0`은 무료다.

**변경안(operation)**은 전체 조건이 아니라 바꿀 항목만 담는다. `SET headcount=40`은 인원을 바꾸고, `CLEAR location`은 장소를 미정으로 되돌린다. 목록에 없는 항목은 유지한다.

**후보(candidate)**는 검증한 변경을 적용한 새 스냅샷이다. 함수가 후보를 만들었다고 DB에 저장한 것은 아니다. BE가 버전·권한을 확인하고 저장해야 한다.

**Structured Output**은 LLM의 답을 정해진 데이터 형식으로 받는 방식이다. “인원을 바꿨습니다”라는 자유 문장 대신 코드가 읽을 수 있는 변경 목록을 받는다. 형식을 지켰다고 의미까지 맞는 것은 아니므로 근거 검증과 실제 모델 평가가 따로 필요하다.

## 3. 한 턴 따라가기: “인원은 40명으로, 장소는 다시 정하자”

### 3-1. 입력 만들기

[schemas.py](../features/planning/schemas.py)의 `ConditionExtractionInput`으로 아래 정보를 묶는다. 예시는 읽기 쉽게 일부 필드만 표시했다.

```text
conditions       = {headcount: 32, location: "가평", fee_per_person: 45000}
current_message  = {id: "m1", role: "user", text: "인원은 40명으로, 장소는 다시 정하자"}
context_messages = []
reference_date   = 2026-10-22
timezone         = Asia/Seoul
event_id         = evt_demo
request_id       = req_demo
base_version     = 3
```

`event_id`는 어느 행사인지, `request_id`는 어느 요청인지, `base_version`은 어떤 버전의 조건을 보고 처리했는지 알려준다. 지금 함수는 이 값을 결과에 보존한다. 실제 DB의 최신 버전과 비교하는 일은 BE 연결 때 구현한다.

이 단계에서는 `headcount=True`, `headcount="32"`, 공백 이름, 잘못된 날짜 등 형식 오류를 막는다. “말한 32명이 작년 인원인가 올해 인원인가?”는 여기서 알 수 없으며 다음 추출 단계가 해석한다.

### 3-2. 모델에 보낼 메시지 만들기

[nodes.py](../features/planning/nodes.py)의 `build_extraction_messages()`는 두 메시지를 만든다.

```python
return [SystemMessage(_system_prompt()), HumanMessage(payload)]
```

- SystemMessage: [extract_conditions.md](../features/planning/prompts/extract_conditions.md)의 추출 규칙.
- HumanMessage: 조건·현재 발화·이전 대화·기준 날짜를 담은 JSON 데이터.

과거 assistant 발화도 JSON의 문맥 데이터로 넣는다. 과거 대화나 문서 속 문장을 새로운 system 지시로 바꾸지 않는다. event_id/request_id/base_version은 모델이 만들 필요가 없어 모델 입력에서 제외하고 코드가 보존한다.

### 3-3. Structured Output으로 변경 목록 받기

호출 경로는 다음과 같다.

```text
extract_condition_changes(request)
  → call_extraction_model(messages)
  → llm.ainvoke_structured(messages, ConditionExtractionOutput)
  → Responses API
  → ConditionExtractionOutput 객체
```

[llm.py](../llm.py)의 핵심 설정은 다음과 같다.

```python
model.with_structured_output(
    schema, method="json_schema", include_raw=True
)
```

Pydantic 타입에서 JSON Schema를 만들고 모델에 기대 형식을 전달한다. 공통 호출 함수는 파싱 성공 여부를 검사한 뒤 타입이 있는 객체를 반환한다. 실제로 읽는 것은 `ConditionExtractionOutput`이다.

이번 예시의 기대 출력은 다음과 같다. 실제 모델 답을 고정하는 예시가 아니라 데이터 흐름을 설명하는 예시다.

```json
{
  "operations": [
    {
      "op": "SET",
      "change": {"field": "headcount", "value": 40},
      "evidence": {"message_id": "m1", "quote": "인원은 40명으로"},
      "offer_id": null,
      "context_evidence": []
    },
    {
      "op": "CLEAR",
      "field": "location",
      "evidence": {"message_id": "m1", "quote": "장소는 다시 정하자"}
    }
  ],
  "unresolved": []
}
```

`evidence`는 이번 사용자 발화의 근거다. `offer_id`와 `context_evidence`는 “그걸로 할게요”처럼 앞선 제안을 수락할 때 쓰며, 직접 지정한 이번 예시에서는 비어 있다.

필드마다 허용하는 값 타입이 다르다. 예를 들어 인원은 양의 정수이고 장소는 문자열이다. 일반 Union과 Literal로 이를 검증한다. discriminated union은 `oneOf`를 생성해 게이트웨이가 거부했으므로 현재는 지원되는 `anyOf`를 사용한다. 타입 제한을 없앤 것은 아니다.

### 3-4. 코드로 검증하고 적용하기

모델 출력은 바로 DB로 가지 않고 `validate_and_apply(request, output)`으로 들어간다.

```python
values = request.conditions.model_dump()
```

먼저 기존 스냅샷의 복사본을 만든다. 그다음 각 변경의 근거가 이번 메시지에 있는지, 같은 필드가 중복되지 않는지 확인한다. SET은 값을 넣고 CLEAR는 `None`을 넣는다.

```text
변경 전: headcount=32, location="가평", fee_per_person=45000
SET 적용: headcount=40
CLEAR 적용: location=None
건드리지 않은 값: fee_per_person=45000
```

마지막으로 `PlanningConditions.model_validate(values)`로 전체 후보를 다시 검사한다. 날짜 두 개를 바꿀 때는 중간 상태가 아니라 최종 날짜 쌍을 검사한다.

출력 `ConditionExtractionResult`의 주요 내용:

```text
status               = APPLIED
candidate_conditions = {headcount: 40, location: None, fee_per_person: 45000, ...}
applied_operations   = [SET headcount, CLEAR location]
unresolved           = []
event_id/request_id/base_version = 입력에서 그대로 복사
```

여기서 APPLIED는 **후보에 반영했다**는 의미다. 저장 완료나 행사 시작 완료를 의미하지 않는다.

## 다음 연결

예를 들어 “인원을 좀 줄이자”는 기존 인원을 보존한 채 headcount/AMBIGUOUS_VALUE를 반환한다. 작업 3은 이 미해결 항목을 받아 몇 명인지 확인하는 질문을 선택할 예정이다. 질문 상태·문구·보류 정책은 작업 3에서 구현한다.
