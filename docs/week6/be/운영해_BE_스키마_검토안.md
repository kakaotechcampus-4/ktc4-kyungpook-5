# BE 스키마 검토안
---

## 1. 변경 요청 7건 — 전부 수용

| # | 요청 | 결과 |
| --- | --- | --- |
| 1 | `steps.phase` 추가 | 적용. 재정렬 API도 바뀝니다 (§4-5) |
| 2 | `events.plan_meta` 추가 | **`plan_warnings` + `plan_excluded_steps` 두 컬럼으로 분리.** `meta`는 아무거나 담기는 이름입니다 |
| 3 | `events.title` `NOT NULL` | 적용 |
| 4 | `actions.deny_reason` 추가 | 적용 |
| 5 | `actions.payload` 추가 | 적용. **`CONFIRMATION` 전용**으로 한정합니다 |
| 6 | `events.end_date` 추가 | 적용. `start_date`도 `datetime` → `DATE`로 맞춥니다 |
| 7 | `events.event_type`·`location` 추가 | 적용 |

## 2. 확인 요청 · 판단 필요 — 답변

| 항목 | 답변 |
| --- | --- |
| 1. 거절에 `approved_*`를 쓰나 | **`resolved_by`/`resolved_at`으로 개명.** 승인·거절·확인요청 선택 셋을 모두 받는 컬럼입니다 |
| 2. `Event.title` / `Conversation.title` | `Conversation.title`은 nullable 유지. 계획 화면 제목은 `Event.title` 기준이 맞습니다 |
| 3. `parse_error` 형식 | 확정 (§4-2) |
| 4. 입출금이 한 열에 섞임 | 스키마가 아니라 파싱 규칙. 별도 이슈 |
| MANUAL 단계가 항상 완료 | `completed` 컬럼을 없애고 `completed_at`·`completed_by`로 판정합니다. 완료 API는 아래 4-6
| `participants` 테이블 | 지적이 맞습니다. 금액 안건과 묶여 범위 밖

## 3. 요청 표에 없던 컬럼 4개 — 함께 추가

FE 명세 본문에는 🔸로 있으나 요청 표에서 빠진 것입니다.

| 컬럼 | 없으면 |
| --- | --- |
| `events.budget_total` · `fee_per_person` · `expected_headcount` | `PATCH /events` 임시 저장이 요청을 받지 못함 |
| `actions.amount` | P2 배지·승인 카드 금액 |

`phases[].description`은 값이 변하지 않아 **컬럼 없이 코드 상수**로 둡니다.

---

## 4. FE 명세를 고쳐야 하는 6건

이 외에는 응답 형태가 그대로입니다.

### 4-1. `approvedAt`/`approvedBy` → `resolvedAt`/`resolvedBy`

### 4-2. `parseError`

서버가 문구를 완성하면 한 글자 고치는 데 배포가 필요합니다. 공통 규약("`code`는 상수, 문구는 FE가 매핑")에 맞춥니다.

```jsonc
{
  "reason": "COLUMN_MISMATCH",     // 코드 상수. FE가 문구 매핑
  "params": { "expectedColumns": [...], "actualColumns": [...] },
  "debugMessage": "..."            // 로그용. 화면에 띄우지 않음
}
```

- `suggestions`는 응답에만 두고 **DB에 저장하지 않습니다.** `reason`에서 유도됩니다
- `reason`에 **`UNKNOWN` 추가.** AI-RET-04가 "원인을 임의로 단정하지 않는다"를 요구합니다
- 값 목록은 파서 구현 시 확정. **추가만 가능**하고 FE는 모르는 값을 `UNKNOWN`으로 폴백합니다

### 4-3. `warnings` — 만든 주체로 나눕니다

규칙이 잡는 것은 코드로, AI가 짚는 것은 문장으로 둡니다. 전부 `code`로 강제하면 예상 못 한 문제를 짚는 AI 경고가 막힙니다.

```jsonc
[
  { "source": "RULE", "code": "SCHEDULE_GAP",
    "params": { "fromStep": "입금 마감", "fromDate": "2026-03-12",
                "toStep": "리허설", "toDate": "2026-03-20", "gapDays": 8 },
    "suggestion": "ADD_CHECKPOINT", "debugMessage": "..." },
  { "source": "AI",
    "message": "작년 MT는 32명이었는데 올해 40명이면 버스 한 대로 부족합니다." }
]
```

`RULE` 경고는 `services/event_rules.py`가 만들고 코드 목록이 유한합니다(NF1과 같은 선).
FE가 모르는 `code`일 때 경고를 숨기지 않도록 `debugMessage`를 폴백으로 둡니다.
`excludedSteps[].reason`은 AI가 만드는 문장이라 그대로 둡니다.

### 4-4. `sources[].location` — 문자열 → 객체

```jsonc
"location": { "label": "회비 수납 시트" }
```

내부 구조(`sheet`·`row`·`page`)는 청킹 방식이 정해져야 나옵니다. 타입만 객체로 열어두면 나중에 필드가 늘어도 FE가 깨지지 않습니다. FE 비용은 `location` → `location.label` 한 군데입니다.

### 4-5. `PATCH /steps:reorder` 요청 형식

`phase`가 생겨 `stepIds`만으로는 묶음 이동을 표현할 수 없습니다.

```jsonc
{ "steps": [ { "stepId": "stp_02", "phase": "PREPARATION" }, ... ] }
```

```jsonc
{ "steps": [
{ "stepId": "stp_02", "phase": "PREPARATION" },
{ "stepId": "stp_01", "phase": "PREPARATION" },
{ "stepId": "stp_03", "phase": "RECRUITING" }
] }
```

### 4-6. 단계 완료 API 신설

`completed_at`을 채울 경로가 필요합니다.

```
POST /api/v1/steps/{stepId}/complete
```

| 항목 | 내용 |
| --- | --- |
| 권한 | `OWNER` / `MANAGER` |
| 요청 | 본문 없음. `completedBy`는 **토큰에서 서버가 채웁니다** |
| 응답 | 갱신된 step + `pendingActionCount` |
| 실패 | `STEP_ALREADY_COMPLETED` (409) |

`stepId`가 전역 유일하고 `POST /actions/{actionId}/approve`가 이미 상위 경로 없이 쓰이므로 `eventId`를 뺐습니다. 동사 표기(`/complete` vs `:complete`)는 콜론 표기 합의 결론을 따릅니다 (§6).

**`actor`와 무관하게 열어둡니다.** 자동으로만 채우면 Action이 실패로 끝난 단계가 영원히 미완료로 남습니다.

```
"입금 확인"  Action 3개 중 2개 DONE, 1개 FAILED
             → 마지막 Action이 DONE이 안 됨 → completed_at 영원히 null
```

문자 발송이 실패해 총무가 직접 보냈다면 그 단계는 끝난 것인데 화면은 계속 진행 중으로 표시합니다. `FAILED`는 명세에 정의된 종료 상태(`APPROVED ──실패──→ FAILED`)라 실제로 발생합니다.

| 채우는 주체 | 언제 | `completed_by` |
| --- | --- | --- |
| 서버 자동 | 그 단계의 Action이 모두 `DONE`이 되는 순간 | `null` |
| 사람 | 완료 API 호출 | 호출자 |

이미 `completed_at`이 있으면 **덮어쓰지 않습니다.** 최초 완료 시점과 처리자를 보존합니다.

**미처리 Action이 남아 있어도 완료할 수 있습니다.** 거부하면 막다른 길이 생깁니다 — 승인 대기 중인 행동을 오프라인으로 처리했을 때 거절(`DENIED`)은 "안 하기로 했다"는 뜻이라 사실과 다릅니다. 서버는 그대로 받고 `pendingActionCount`를 응답에 실어 보냅니다. "미처리 2건이 남아 있습니다. 완료하시겠습니까?" 같은 확인은 FE 몫입니다.

> ⚠️ **완료 표시와 진행률은 어긋날 수 있습니다.** 완료 판정은 `completed_at`, 진행률은 Action 개수라
> `[✓ 완료] 입금 확인 2/4` 같은 상태가 정상적으로 발생합니다. 완료된 단계는 막대를 숨기거나
> "4개 중 2개 처리 · 완료됨"처럼 문구를 구분해 주세요. **화면 결정은 FE 몫**입니다.

되돌리기(`:reopen`)는 두지 않습니다. `completed_at`을 `null`로 되돌리는 것뿐이라 나중에 추가해도 마이그레이션이 없습니다.

---

## 5. 회의 · 확인이 필요한 것

### 팀 확인 필요 - 이미 코드에 반영함.

| 항목 | 내용 |
| --- | --- |
| **enum 문자열 저장** | `Integer(매크로 변수)` → `VARCHAR(32)` 코드 문자열. 변환 계층이 사라져 코드가 줄고 **API 응답은 그대로**입니다 |
| **날짜 타입** | 회의록은 전부 `datetime`이었으나 명세를 따라 `start_date`·`end_date`·`due_date`를 `DATE`로. `deadline`은 `TIMESTAMPTZ`("3/12 14:59") |
| **`conversation.user_id`** | `users` 테이블이 없어 FK 대상이 없었습니다. `member_id`로 개명 |

### 아직 정해지지 않은 것

| 항목 | 내용 | 대상 |
| --- | --- | --- |
| 인원 필드명 | `GET /events/{id}`는 `headcount`, `PATCH /events`는 `expectedHeadcount`. 같은 값에 두 이름 | FE |
| `locationCandidates` | 계획 중 장소 후보가 여러 개인데 `events.location`은 단수입니다 | FE·BE |
| `collectionPlan.times` | 수금 횟수를 담을 컬럼이 없습니다 | FE·BE |
| `title` 기본값 | `새 행사 · 3월 2일`이면 같은 날 두 개를 만들 때 구분이 안 됩니다. `NOT NULL`로 바꾼 목적이 무너집니다 | FE·BE |
| 규칙 경고 `code` 목록 | 초안: `SCHEDULE_GAP`·`BUDGET_EXCEEDED`·`PREP_TIME_SHORT`·`SCHEDULE_CONFLICT`·`MINIMUM_HEADCOUNT_VIOLATED` | BE |
| 동시 승인 | 임원 둘이 동시에 승인할 때 조건부 `UPDATE`가 필요합니다. AI-OPS-03이 중복 실행 금지를 요구합니다 | BE |
| 네이밍 | `steps.started_time`만 `_time`이고 과거형인데 값은 예정 시각. `steps.name` vs `actions.title` | 팀 |
| 임베딩 모델 | RAG 청크의 `vector(N)` 차원이 여기 달립니다. Anthropic은 임베딩 API가 없어 별도 제공자가 필요하고 pgvector 인덱스는 2000차원까지입니다 | 팀 |

---

## 6. 이번 범위 밖

| 항목 | 이유 |
| --- | --- |
| `participants` · `transactions` | 금액 안건 미확정. 없으면 미납자 산출과 `event_rules.py`의 입력이 없습니다 → #15 후속 |
| 승인 이력 테이블 | `actions.status` 덮어쓰기는 NF4와 어긋나나, append-only 테이블은 나중에 추가해도 기존 컬럼을 건드리지 않습니다. 승인 정책(D-05) 확정 후 |
| RAG 청크 테이블 | 저장소는 **pgvector 확정**. 임베딩 모델 미정이라 차원을 정할 수 없습니다. `sources[].location` 내부 구조도 여기서 함께 정합니다 |
| `events.planning_conversation_id` | 대화가 여러 개일 때 복원 대상 규칙. 현재는 가장 최근 대화. AI-PLAN-08 구현 시 |
| `auth` 테이블 재구성 | 신원과 세션이 한 행에 섞여 로그인마다 행이 쌓입니다. 인증 방식(JWT vs 세션) 확정 후 |
| 파일 원본 조회 API | `storage_key`는 있으나 원본을 보거나 내려받을 엔드포인트가 없습니다 |
| Alembic 마이그레이션 | DB가 아직 없습니다. 첫 배포 직전에 초기 리비전 1개 |
| 장부 파싱 규칙 | 확인 요청 4번 |

### 라우터 구현 시 정할 것

- **"처리된 승인" 조회 조건** — `approve_needed=false`인 행동은 `APPROVED`를 건너뛰고 `DONE`이 되므로 `status=APPROVED,DONE,DENIED`에 **아무도 승인하지 않은 건이 섞입니다.** `approve_needed=true`가 필요합니다
- **`excludeType` 파라미터** — FE가 임시로 제안한 것
- **콜론 표기** — `:generate` · `:confirm` · `:reorder`가 명세에 "팀 합의 필요"로 남아 있습니다. §4-6의 완료 API 동사 표기도 이 결론을 따릅니다
