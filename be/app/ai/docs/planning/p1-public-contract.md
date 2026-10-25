# P1 공개 계약 초안 — BE가 보내는 것과 AI가 돌려주는 것

상태: **1번 명세와 2번 데이터 타입/상태 변환 구현. 3번 공개 실행 함수까지 연결했다. 제품 BE 연동은 미구현이며 팀 합의 전이다.**

구현 이슈: [#180](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/180). 코드의 기준은 `planning_contracts.py`이며 저장 JSON 형식 버전은 1이다.

관련: [협업 이슈 #179](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/179), [P1 인계 안내](p1-handoff.md). 요구사항: AI-PLAN-01~05, AI-PLAN-08, AI-COMMON-02.

## 1. 이번에 정하는 것

BE가 `app.ai`만 import해서 P1 대화를 이어갈 수 있도록 입력과 출력의 책임을 정한다. 내부 Agent를 새로 만드는 작업이 아니다. 기존 대화 Graph와 생성 Graph 앞에 공개 계약과 변환 계층을 둔다.

이번 문서는 공개 입출력과 상태 보관 방향을 제안한다. 2번에서 데이터 타입과 직렬화 코드를 추가했다. 3번에서 공개 실행 함수를 연결했다. DB 컬럼과 HTTP 경로는 추가하지 않았다. P2 단계 삭제와 순서 변경, 운영 Agent도 이번 범위에 넣지 않는다.

```text
사용자: “일단 인원은 대략 50명으로 하자”
  FE → BE: 사용자 메시지
  BE → app.ai: 현재 조건 + 이번 메시지 + 이전 Agent 상태
  app.ai → 기존 대화 Graph: 내부 타입으로 변환해 실행
  app.ai → BE: 화면용 결과 + 다음 Agent 상태
  BE: 조건, 답변, 상태를 같은 요청 결과로 저장
  BE → FE: 답변과 50명 잠정 표시
```

`app.ai` 공개는 BE 내부 Python 인터페이스를 뜻한다. FE가 AI 모듈이나 모델 서버를 직접 호출하는 API를 뜻하지 않는다.

## 2. 공개 기능은 두 가지로 구분한다

아래 두 실행 함수와 요청/결과 타입, `parse_resume_state`를 `app.ai`에서 import할 수 있다. 제품 HTTP 계약은 BE/FE 협의 전이다.

| 공개 기능 제안 | 입력 계기 | 기존 코드 연결 | 결과 |
| --- | --- | --- | --- |
| `chat_planning` | 사용자가 메시지를 보냄 | `run_planning_agent_turn()` | 답변, 현재 조건, 검색/생성 결과, 다음 상태 |
| `generate_planning_preview` | 「다음: 흐름 만들기」 클릭 | `run_button_plan_generation()` | 생성 결과, 현재 조건, 다음 상태 |

채팅에서 생성 권유를 수락하면 Agent의 생성 Tool을 거친다. 버튼은 의도 해석이나 가짜 사용자 메시지 없이 같은 생성 기능으로 연결한다. 버튼 응답에 AI 말풍선을 필수로 만들지 않는다.

행사별 상태는 요청 사이에도 BE에 보관한다. 공개 함수는 같은 행사 Agent에 신호를 전달하고 결과를 받는 경계다. 매번 이력 없는 새 Agent를 만드는 의미가 아니다. 상시 프로세스나 운영 신호 스케줄러 구현은 이번 작업과 별개다.

## 3. BE가 보내는 입력

### 공통 정보

| 필드 제안 | 의미 | 누가 준비하나 |
| --- | --- | --- |
| `request_id` | 이번 처리의 식별자 | BE. 같은 요청 재전송은 같은 ID 사용 |
| `event_id`, `conversation_id`, `club_id` | 어느 행사와 대화인지, 검색 가능한 동아리 | BE가 권한과 소속을 확인해 설정 |
| `base_revision` | 읽어 온 상태의 버전 | BE. 결과 저장 전 다른 요청이 먼저 변경했는지 확인 |
| `draft` | 현재 조건, 잠정 여부, 보류 주제 | BE가 저장된 값을 공개 타입으로 변환 |
| `resume_state` | 앞선 대화와 생성 권유 등을 이어갈 상태 | BE가 이전 AI 결과를 보관했다가 전달. 최초에는 null |
| `reference_date`, `timezone` | “다음 달” 등을 해석할 기준 | BE. 날짜는 YYYY-MM-DD, 시간대 기본 제안은 Asia/Seoul |

채팅은 `message: {id, content}`를 추가한다. role은 사용자로 고정하고 이번 메시지를 이전 이력에 중복해서 넣지 않는다. 요청 ID와 메시지 ID는 목적이 다르므로 별도 필드로 둔다. 내부 생성 Tool이 메시지 ID를 사용하는 점은 어댑터에서 연결한다.

버튼에는 `message`가 없다. `use_current_conditions`는 기본 false로 제안한다. 반영되지 않은 변경이 있을 때 사용자가 **기존 값으로 생성하겠다고 명시적으로 확인한 경우**에만 true를 보낸다. 버튼을 눌렀다는 이유만으로 자동 설정하지 않는다.

### 조건 값의 의미

`draft`는 현재 내부 `PlanningDraft`의 의미를 유지하되 BE가 내부 모듈을 import하지 않아도 되는 공개 타입으로 제공할 예정이다.

| 항목 | 표현 |
| --- | --- |
| 행사 조건 | `title`, `event_type`, `headcount`, `fee_per_person`, `start_date`, `end_date`, `location`, `budget_total` |
| 미정 | null. 생략된 변경값이나 0원과 혼동하지 않기 |
| 무료 | `fee_per_person: 0` |
| 잠정 인원 | `headcount: 50` + 해당 필드의 `status: tentative` |
| 명시한 값 | `status: specified`. 행사 최종 승인이라는 뜻은 아님 |
| 날짜 보류 | `deferred_topics`에 `dates`. 날짜 값이 null인 것과 별도 정보 |
| 근거 | 조건 메타에 발화 근거 보관. FE에 노출할 범위는 BE가 변환 |

인원은 1 이상 정수, 금액은 0 이상 정수다. 날짜 순서 등 현재 검증을 유지한다. 예산은 명시된 예산 상한이며 인원 × 참가비를 자동으로 확정 예산에 넣지 않는다.

BE의 `expected_headcount`와 AI의 `headcount`는 어댑터에서 변환한다. BE의 필수 Event 제목을 AI의 null로 덮어쓰지 않는다. 기본 제목과 사용자 지정 제목의 구별은 BE 협의 항목이다.

## 4. AI가 돌려주는 출력

결과는 `view`와 `next_state`로 분리하는 안을 제안한다. `view`도 최종 HTTP DTO는 아니다. BE가 권한, 저장 ID, 필드명에 맞춰 FE 응답으로 변환한다.

| 영역 | 필드 제안 | 용도 |
| --- | --- | --- |
| 요청 연결 | `request_id`, `base_revision` | 어느 입력으로 만든 결과인지 확인. AI가 DB 버전을 증가시키지 않음 |
| 화면용 `view` | `reply` | 채팅 답변. 버튼 경로에서는 null 허용 |
| 화면용 `view` | `draft` | 처리 후 조건 전체 스냅샷. FE가 답변에서 숫자를 추출하지 않음 |
| 화면용 `view` | `changed_fields` | 요청 draft와 최종 draft의 조건 값 차이. 코드로 계산 |
| 화면용 `view` | `record_lookup` | 이번 검색 결과, 출처, 자료 없음, 실패. 검색 안 했으면 null |
| 화면용 `view` | `generation_readiness` | 코드로 판단한 생성 가능 여부와 차단 사유 |
| 화면용 `view` | `generation_result` | 이번 생성의 generated / needs_clarification / failed. 생성 안 했으면 null |
| 화면용 `view` | `preview_is_current` | 보관된 초안이 현재 조건 기준인지 여부 |
| BE 보관용 | `next_state` | 다음 요청에서 돌려줄 Agent 상태 |

`changed_fields`는 값 변경 알림용 보조 정보다. 값이 그대로여도 잠정 여부나 보류 주제는 바뀔 수 있으므로 **화면은 항상 반환된 draft 전체로 갱신**한다. 단계 편집 명령이나 DB patch로 쓰지 않는다.

생성 가능 여부는 행사 유형, 유효한 조건, 미해결 변경 여부를 공통 코드로 확인한다. 날짜와 인원이 미정이어도 허용한다. LLM이 생성 권유를 했는지는 별도 상태이며 버튼 활성화 조건이 아니다. 공개 변환에서도 별도 규칙을 중복 작성하지 않도록 공통 판정 함수를 마련할 예정이다.

생성 성공에만 이번 preview가 있다. 이전 성공 초안은 next_state에 보존되며, 이번 실패를 이전 초안의 성공으로 표시하면 안 된다. 재접속 때 마지막 초안을 화면으로 복원하는 투영 방법도 공개 어댑터에서 제공할 필요가 있다. 초안의 상세 필드는 [P2 계약](p2-data-contract.md)을 따로 맞춘다.

## 5. 이어가기 상태는 BE가 보관하고 AI가 해석한다

쉽게 말하면 `view`는 **화면에 보여줄 결과**, `next_state`는 **Agent가 다음 대화를 이어갈 작업 기록**이다.

상태 봉투는 `schema_version`, 행사/대화 소속, `payload`를 가진 JSON 형태를 제안한다. payload에는 대화 및 Tool 호출/결과, 생성 권유, 마지막 초안, 미해결 조건 변경 정보, 이전 조건 기준이 필요하다. API 키, 프롬프트 설정, SDK 객체 자체나 실행 가능한 pickle은 저장하지 않는다.

- AI는 JSON으로 저장했다가 복원할 수 있는 직렬화와 검증을 책임진다. Tool 호출 ID와 결과의 짝을 유지한다.
- BE는 payload 내부를 편집하지 않고 저장 후 그대로 반환한다. FE로 전체 상태를 보내거나 FE에서 받은 상태를 신뢰하지 않는다.
- 최초 null만 새 상태를 뜻한다. 알 수 없는 형식 버전이나 손상된 상태는 조용히 초기화하지 않고 복원 불가로 알린다.
- 다른 행사/대화의 상태를 재사용하지 못하도록 소속을 검증한다. 이는 BE 권한 검사를 대체하지 않는다.
- 현재 draft는 BE가 전달한 값이 기준이다. 상태 안의 과거 조건으로 덮어쓰지 않는다.
- 상태의 이전 조건 기준과 현재 draft가 다르면 외부 변경으로 식별한다. 권유와 초안의 기준을 그대로 유효하다고 간주하지 않는다. 초기 연결에서는 불일치를 명시적으로 반환하고, 동기화 정책을 합의하기 전 임의로 대화를 계속하지 않는 안이다.

draft를 입력에도 두는 이유는 Event가 조건의 기준이고 Agent 상태는 대화 기록이기 때문이다. 대신 BE는 조건과 상태를 **같은 결과로 함께 저장**해야 한다. FE의 직접 조건 편집 경로는 아직 합의되지 않았으므로 별도 동기화 계약 없이 병행하지 않는다.

현재 내부 입력은 Tool 메시지를 포함해 history 최대 60개다. 결과 이력이 다음 입력 한도를 넘을 수 있는 경계까지 검증해야 한다. 공개 전에 반환 상태가 다음 요청에서 복원 가능한지 확인하고, 초과 시 명시적 제한 안내를 정의한다. 임의 절단이나 자동 대화 초기화는 하지 않는다. 장기 대화 요약은 별도 과제이며 아직 지원된다고 안내하지 않는다.

## 6. 예시로 따라가기

아래는 계약의 의미를 보여주는 축약 예시이며 실행 가능한 완성 DTO가 아니다. 답변 문구와 모델 판단은 고정 응답이 아니다.

### 예시 A. 상담 후 짧은 수락

```text
현재: 참가비 25,000원, 저장된 상태 S0

입력 1: “3만 원이면 어때?” + draft(25,000원) + S0
  → 공개 어댑터가 내부 PlanningAgentTurnInput으로 변환
  → run_planning_agent_turn(): 상담 답변, 조건 변경 없음
출력 1: view(답변, 참가비 25,000원) + next_state S1
  → BE가 S1과 답변 저장

입력 2: “일단 그렇게 잡자” + draft(25,000원) + S1
  → S1의 앞선 상담을 복원
  → Agent가 update_event_conditions Tool 선택
  → 근거와 값 검증 후 참가비를 잠정 30,000원으로 반영
출력 2: view(답변, 참가비 30,000원 잠정) + next_state S2
  → BE 저장 → FE 조건 카드 갱신
```

S1 대신 말풍선 하나만 전달하면 “그렇게”의 대상을 잃을 수 있다. 그래서 응답 텍스트와 Agent 상태를 구분해 보관한다.

### 예시 B. 채팅 수락과 버튼

```text
채팅: 저장된 생성 권유 + “응, 만들어줘”
  → chat_planning → 대화 Agent → 생성 Tool ┐
                                            ├→ 공통 생성 Graph
버튼: 현재 draft + 저장된 상태 + 클릭 요청 ID │
  → generate_planning_preview ───────────────┘

generated → BE가 결과 저장 → FE가 P2로 이동
failed → 조건과 이전 초안 유지 → 실패 안내, P1에서 재시도 가능
```

P1의 “예약 단계는 빼줘”를 별도 편집 요구로 추출해 최초 생성에 적용하지 않는다. 단계 제외와 순서 변경은 생성 후 P2에서 한다.

## 7. 실패와 중복 요청

| 상황 | AI 계약 방향 | BE/FE 처리 |
| --- | --- | --- |
| 검색 자료 없음 | record_lookup의 not_found | 대화 계속, 자료 없음 표시 |
| 검색 실패 | record_lookup의 failed | 자료 없음과 구분, 현재 조건 유지 |
| 조건 반영 성공 후 생성 실패 | 정상 턴 결과 안에 generation_result.failed | 새 조건과 다음 상태 저장, 생성만 실패 안내 |
| 대화 전체 호출 실패 | 기존 AI 오류 체계로 전달 | 이전 상태 보존. 중간 Tool 결과를 성공 저장하지 않음 |
| 상태 손상/형식 미지원/조건 불일치 | 공개 경계에서 모델 호출 전 구별 가능한 오류 필요 | 자동 초기화 금지. 복원/동기화 절차로 처리 |
| 저장 전 revision 변경 | BE가 충돌 판정 | 오래된 결과로 덮어쓰기 금지 |

공개 입력 오류와 복원 오류의 구체 타입은 구현 이슈에서 정한다. 공급자 오류 원문을 그대로 FE에 전달하지 않는다. HTTP 상태 코드는 BE가 결정한다.

BE는 요청 ID별 처리 결과를 관리한다. 완료된 동일 요청은 저장된 결과를 재사용하고, 같은 ID에 다른 입력을 보내면 거절한다. 생성 내부의 마지막 성공 요청 재사용 기능만으로 전체 대화 중복 처리가 보장되는 것은 아니다. 실패 후 재시도 정책과 메시지 중복 방지는 BE와 함께 맞춘다.

AI는 결과를 제안할 뿐 DB에 저장하지 않는다. 반환 직후 프로세스가 끊긴 상황과 저장까지 완료된 상황도 BE가 구분한다.

## 8. 구현 전에 맞출 항목

| 항목 | 이번 제안 | 협의 대상 |
| --- | --- | --- |
| 상태 보관 | JSON 상태를 BE가 보관, AI가 형식과 변환 관리 | BE: 보관 위치와 크기/보존 정책 |
| 요청 순서 | 같은 행사 요청 직렬화 또는 revision 검사, 결과 중복 방지 | BE |
| 화면 응답 | draft 전체, 잠정/보류, 출처, 생성 상태 전달 | BE/FE: HTTP 이름과 표시 방식 |
| 조건 직접 편집 | 대화 상태와 동기화되는 별도 경로 필요 | BE/FE: 실제 P1 편집 UI 유무 |
| 검색 주입 | 기존 RecordSearchPort 재사용, 권한 확인한 club_id로 제한 | BE: 실제 검색 구현 연결 |
| 제목/장소 | 기본 제목과 null 구분, location 단일 값 | BE/FE |
| 긴 대화 | 한도를 숨기지 않고 명시적 처리, 자동 절단 금지 | AI/BE: 최초 연결 한도와 후속 요약 |

이 항목들은 팀 합의 완료로 표시하지 않는다. 공개 함수는 내부 모듈 경로를 BE에 노출하지 않으며 테스트용 HTTP API를 재사용하지 않는다.

## 9. 다음 구현 작업과 확인 기준

AI 구현 이슈 [#180](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/180)에서 데이터 타입과 상태 변환을 진행했다. 이 문서와 #179를 선행 자료로 사용한다. 아래는 공개 연결 전체의 확인 항목으로, 이후 facade 연결과 실제 검색 주입 및 BE 연결 검증을 이어간다.

- [x] 공개 요청/결과/상태 타입을 정의한다. 실행 사용처가 없던 이전 대화 계약은 #182에서 제거했다.
- [x] SDK 객체 없이 JSON 왕복 복원하고 Tool 호출/결과 짝을 보존한다.
- [x] 위 상담 → 저장 → 짧은 수락 예시를 복원 후 검증한다.
- [x] 행사/대화 소속, 상태 버전, 손상된 payload, 외부 조건 변경을 구분한다.
- [x] history 한도 경계에서 반환 상태가 다음 입력으로 가능한지 확인한다.
- [ ] 채팅과 버튼이 같은 생성 규칙을 사용하고 버튼이 가짜 발화를 만들지 않는지 확인한다.
- [ ] 일부 실패와 전체 실패에서 보존할 상태가 다름을 확인한다.
- [ ] 최종적으로 BE가 `app.ai`만 import하는 연결 테스트를 통과한다.

1번 문서 작업과 2번 데이터 계약 구현은 공개 실행 API 완성과 구분한다. 3번에서 `app.ai.__init__`에 두 실행 함수를 연결했다. 검증에서 모델 응답은 고정했으며 실제 모델 품질이나 제품 연결을 검증한 것은 아니다.


## 10. 2번 작업에서 실제로 구현한 흐름

```text
PlanningChatRequest                  ← BE가 만드는 입력
  → to_agent_input()                 ← 저장 이력을 SDK 메시지로 복원
  → run_planning_agent_turn()        ← 기존 Graph와 Tool 실행 (공개 facade에서 연결)
  → capture_turn_state()             ← 결과를 JSON 저장 가능한 형태로 변환
  → state.model_dump_json()          ← BE가 저장할 문자열

다음 요청:
  parse_resume_state(저장 문자열)
  → 새 PlanningChatRequest의 resume_state에 전달
  → 앞선 상담과 생성 권유를 이어서 사용
```

공개 타입은 [planning_contracts.py](../../planning_contracts.py), 내부 변환 함수는 [state_codec.py](../../features/planning/state_codec.py)에 있다. BE는 내부 변환 함수를 직접 호출하는 제품 코드를 만들지 않는다. 3번에서 공개 facade가 이 순서를 묶었다.

`PlanningPublicResult`는 화면용 `view`와 보관용 `next_state`를 나눈다. 두 조건이 다르면 검증 오류가 난다. 3번에서 화면용 결과 구성, 공통 생성 가능 판정, 버튼 실행을 연결했다. 대화 턴은 capture_turn_state를 쓰고, 버튼은 이력을 유지하며 생성 상태만 갱신한다.

### 읽어볼 핵심 코드

```python
# 지금 app.ai에서 사용 가능한 데이터 계약과 복원 함수
from app.ai import PlanningChatRequest, PlanningUserMessage, parse_resume_state

# BE가 보관한 JSON을 다음 요청에서 복원한다.
state = parse_resume_state(saved_json)
request = PlanningChatRequest(
    request_id="request-2", club_id="club-1", event_id="event-1",
    conversation_id="conversation-1", base_revision=1,
    draft=current_draft, resume_state=state,
    reference_date="2026-10-25",
    message=PlanningUserMessage(id="message-2", content="일단 그렇게 잡자"),
)
# saved_json/current_draft는 BE가 같은 결과로 저장했던 값이다.
# 실제 호출은 아래 11절의 chat_planning 예시를 따른다.
```

- `PlanningRequestContext.validate_resume`: 상태의 동아리/행사/대화와 현재 요청이 일치하는지, 조건이 동기화됐는지 검사한다. BE 권한 검사를 대신하지 않는다.
- `PlanningStatePayload.validate_pairs`: Tool 호출만 있고 결과가 없는 잘린 이력을 거절한다.
- `capture_turn_state`: 사용자/AI/Tool 메시지에서 다음 대화에 필요한 필드를 골라 저장한다. 공급자 응답 메타데이터는 제외한다. 원본 결과를 나중에 바꿔도 보관 상태가 바뀌지 않도록 복사한다.
- `parse_resume_state`: 미지원 버전은 `unsupported_version`, 손상은 `invalid_state`인 `PlanningStateError`로 구분한다. 직접 요청 모델을 만들 때의 검증 실패는 Pydantic `ValidationError`이며 내부 원인 context에 상태 오류가 담긴다.

### 검증한 것과 남은 것

실제 LangGraph에 고정 모델 응답을 주입해 상담 → JSON 저장 → 복원 → 짧은 수락 → 조건 Tool 실행을 확인했다. 25,000원이 첫 턴에는 유지되고 두 번째 턴에는 30,000원 잠정으로 바뀐다. 이는 저장/복원과 실행 연결의 검증이며 실제 LLM이 모든 수락 표현을 정확히 해석한다는 평가는 아니다.

다른 행사 상태, 조건 불일치, 손상 JSON, 미지원 버전, Tool 결과 누락, 중복 메시지, 60/61개 이력 경계, 버튼에 가짜 메시지를 넣는 경우를 함께 검증한다. 60개를 복원할 수 있어도 다음 턴 후 60개를 넘으면 캡처를 거절한다. 장기 대화 요약이 연결되기 전의 제한이며 자동으로 이력을 버리지 않는다.

3번에서 공개 facade를 연결했다. BE가 내부 모듈을 import하지 않고 호출할 수 있으며, 실제 DB/권한/HTTP 연결 검증은 남아 있다.

검증 기록: 2026-10-25, AI 테스트 718개 통과(이번 상태 계약 테스트 20개 포함). 기존 별도 작업 파일 `test_planning_records_evaluation.py`는 이번 회귀 실행에서 제외했다.


## 11. 3번 작업: 공개 함수로 실행하기 (#181)

[구현 이슈 #181](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/181). 공개 계약은 팀 협의 전 초안이며 실행 함수까지 구현한 상태다.

```python
from app.ai import chat_planning, generate_planning_preview, PlanningPreviewRequest

# request는 10절의 PlanningChatRequest다.
result = await chat_planning(request, records=record_search_port)
# BE: revision 확인 후 result.view.draft, 답변, 아래 상태를 함께 저장한다.
saved_json = result.next_state.model_dump_json()
# FE: result.view를 제품 응답으로 변환해서 표시한다.

# 별도 버튼 요청. 메시지를 만들어 채팅에 추가하지 않는다.
click = PlanningPreviewRequest(
    request_id="click-1", club_id=request.club_id, event_id=request.event_id,
    conversation_id=request.conversation_id, base_revision=saved_revision,
    draft=result.view.draft, resume_state=result.next_state,
    reference_date=request.reference_date, timezone=request.timezone,
)
preview_result = await generate_planning_preview(click)
# 이번 generation_result.status가 generated일 때 P2로 이동한다.
```

위 예시는 async 서비스 안에서 실행하며 `record_search_port`와 `saved_revision`은 BE가 준비한다. 공개 함수가 저장하거나 revision을 증가시키지 않는다.

### 입력 → 핵심 코드 → 결과

1. `facade.chat_planning` → [public_workflow.chat](../../features/planning/public_workflow.py): 공개 요청을 다시 검증하고 실행용 복사본을 만든다.
2. `to_agent_input`: 상태를 복원한다. `run_planning_agent_turn`이 기존 Graph와 Tool을 실행한다.
3. `capture_turn_state` → `build_result`: 저장 상태와 화면 응답을 만든다. `changed_fields`는 실제 값 차이로 계산한다.
4. 버튼은 `generate_preview` → `run_button_plan_generation`으로 간다. 복원된 대화와 최신 검색 근거를 사용하되 새 메시지는 추가하지 않는다.
5. 생성 권유, 화면의 생성 가능 여부, 실제 생성 차단은 `generation/readiness.py`의 같은 조건 함수를 사용한다. 미정 날짜/인원은 차단 조건이 아니다.

`records`를 생략하면 검색 Tool 자체를 제공하지 않는다. 제품에서는 BE가 기존 RecordSearchPort 구현을 주입한다. AI는 요청의 club_id로 검색 어댑터를 묶고 현재 행사 ID로 과거 자료를 제한하지 않는다. 실제 조회 권한 검사는 BE 책임이다. 버튼은 새 검색을 수행하지 않고 저장된 최신 검색 근거만 사용한다.

조건 변경 성공 후 생성만 실패하면 새 조건과 실패 결과를 함께 반환한다. 대화 전체가 예외로 끝나거나 상태 한도를 넘으면 정상 결과를 반환하지 않으며 입력은 보존한다. BE는 실패한 요청의 중간값을 저장하지 않는다.

### 상태 복원 보완

#180 상태에는 메시지 이름이 빠져 있었다. `latest_reference_facts`는 이름이 search_past_events인 Tool 결과를 찾으므로, 저장 후 버튼 생성에서 근거가 사라질 수 있었다. 이번에는 선택 필드 `name`을 저장하고 복원한다. 기존 형식 버전 1의 JSON도 읽을 수 있지만, 이름이 이미 빠진 과거 상태의 검색 근거는 자동 복구하지 않는다. 필요한 경우 새로 검색한다.

### 검증 범위

공개 함수에서 조건 변경 후 저장/복원, 권유 수락 생성, 버튼 생성과 성공 요청 재사용, 행사 유형 누락, 미해결 변경 확인, 검색 범위 전달, 검색 근거 복원 후 버튼 생성, 부분 실패와 전체 실패를 검증한다. 기존 Graph는 실제 실행하고 모델 응답과 검색 결과를 고정한다. 실제 공급자 모델이나 제품 DB 연결 검증은 아니다.

검증 기록: 2026-10-25, 새 공개 실행 테스트 11개 포함 AI 테스트 729개 통과. 별도 작업인 `test_planning_records_evaluation.py`는 회귀 실행에서 제외했다.
