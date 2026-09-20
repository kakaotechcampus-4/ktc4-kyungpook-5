# 운영해 · FE API 명세 v1

> 작성 기준: 2026-09-18 확정된 BE 스키마 (Club / Member / Auth / Event / Step / Action / Record / AgentLog / Conversation / Message)
> + 2026-09-19 `운영해_BE_스키마_검토안.md` §4 반영
> Figma v5 기준
>
> **v1에서 바뀐 것 (초안 대비)** — `운영해_BE_스키마_검토안.md` §4 "FE 명세를 고쳐야 하는 6건" 반영
> 1. `approvedAt`/`approvedBy` → `resolvedAt`/`resolvedBy`
> 2. `parseError` 형식 확정 (`reason`/`params`/`debugMessage`, `UNKNOWN` 추가)
> 3. `warnings`를 `source`(`RULE`/`AI`) 기준으로 분리
> 4. `sources[].location` — 문자열 → 객체 (`{ "label": "..." }`)
> 5. `PATCH /steps:reorder` 요청 형식 변경 (`stepIds` → `steps[].{stepId,phase}`)
> 6. 단계 완료 API 신설 (`POST /steps/{stepId}/complete`)
> 7. 인원 필드명을 `headcount`로 통일 (`PATCH /events`의 `expectedHeadcount` → `headcount`)
>
> **표기**
> 🔸 = **현재 BE 스키마에 없는 필드.** FE가 화면을 기준으로 필요하다고 판단해 임시로 넣은 것이며, **BE와 합의된 바 없습니다.**
> 응답 자리만 잡아두고 값은 `null`로 내려온다고 가정합니다. 전체 목록과 사유는 별도 문서 `BE_스키마_검토요청.md` 참고.
> ⏸ = 엔드포인트 자체를 보류. 정의하지 않음.
>
> 위 6건 외의 🔸 표시는 초안과 동일하게 유지합니다 (스키마 확정 반영은 별도 작업).

---

## 공통 규약

### 응답 봉투

```jsonc
// 성공 (단건)
{ "data": { ... }, "meta": null }

// 성공 (목록 · 페이지네이션 있음)
{ "data": [ ... ], "meta": { "page": 1, "size": 10, "totalCount": 12 } }

// 성공 (목록 · 페이지네이션 없음)
{ "data": [ ... ], "meta": null }

// 실패
{ "error": { "code": "EVENT_NOT_FOUND", "message": "해당 행사를 찾을 수 없습니다." } }
```

| 항목 | 규칙 |
| --- | --- |
| Base path | `/api/v1` |
| JSON 키 | camelCase (BE에서 변환) |
| 날짜 | `date`는 `YYYY-MM-DD`, `datetime`은 ISO 8601 UTC |
| enum | **문자열 코드로 내려줌** (DB는 SmallInteger지만 API 경계에서 변환) |
| 금액 | 정수(원 단위) |
| 페이지네이션 | `?page=1&size=20`, page는 1부터 |
| `meta` | **페이지네이션이 있는 목록만** 채움. 그 외 배열·단건은 `null` |
| 204 | `DELETE` 성공은 본문 없이 204. 봉투 예외 |
| 인증 | 모든 요청에 `Authorization: Bearer {accessToken}` |
| 권한 | 승인·계획 변경은 `OWNER` / `MANAGER`만. 항목별 가능 여부는 응답의 `canApprove`로 내려줌 |

### enum 코드값

| enum | 값 |
| --- | --- |
| `EventStatus` | `PLANNING` / `ON_GOING` / `COMPLETE` |
| `StepActor` | `AI` / `APPROVAL_REQUIRED` / `MANUAL` |
| `StepPhase` | `PREPARATION` / `RECRUITING` / `EXECUTION` — 🔸 `steps.phase` 없음 |
| `EventType` | `MT` / `WELCOME` / `PICNIC` / `ACADEMIC` / `WORKSHOP` / `ETC` — 🔸 저장 위치 미정 |
| `ActionType` | `EXTERNAL_SEND` / `TRANSFER` / `EXPENSE` / `CONTRACT` / `NOTICE` / `CONFIRMATION` |
| `ActionStatus` | `PENDING` / `APPROVED` / `DENIED` / `DONE` / `FAILED` |

**`ActionStatus` 전이**

```
PENDING ──승인──→ APPROVED ──Agent 실행 완료──→ DONE
   │                              └──실패──→ FAILED
   └──거절──→ DENIED

(approve_needed=false)  PENDING ──Agent 실행 완료──→ DONE
```

`APPROVED`는 **사람이 승인했지만 Agent가 아직 실행하지 않은** 상태입니다.
Agent가 모든 처리를 끝내면 `DONE`이 됩니다. 승인이 필요 없는 행동은 `APPROVED`를 거치지 않고 바로 `DONE`이 됩니다.
| `RecordCategory` | `LEDGER` / `PLAN` / `NOTICE` / `ETC` |
| `RecordFileType` | `XLSX` / `CSV` / `HWP` / `PDF` / `IMAGE` |
| `RecordParseStatus` | `PARSING` / `NEEDS_REVIEW` / `COMPLETED` / `INDEXED` / `FAILED` |
| `MemberRole` | `OWNER` / `MANAGER` / `MEMBER` |
| `MessageRole` | `USER` / `ASSISTANT` / `SYSTEM` |
| `StepState` | `DONE` / `CURRENT` / `TODO` — **DB 컬럼 아님. 서버가 계산해 내려주는 값** |
| `DraftStage` | `CHAT` / `FLOW` — **DB 컬럼 아님. Step 개수로 서버가 계산** |

### 에러 코드

| code | HTTP | 상황 |
| --- | --- | --- |
| `VALIDATION_FAILED` | 422 | 입력 검증 실패. `fields` 포함 |
| `UNAUTHORIZED` | 401 | 토큰 없음·만료 |
| `FORBIDDEN` | 403 | 권한 없음 |
| `EVENT_NOT_FOUND` | 404 | |
| `RECORD_NOT_FOUND` | 404 | |
| `ACTION_NOT_FOUND` | 404 | |
| `ALREADY_RESOLVED` | 409 | 이미 승인·거절된 Action |
| `EVENT_NOT_PLANNING` | 409 | PLANNING 상태가 아닌 행사에 계획 API 호출 |
| `PLAN_INCOMPLETE` | 409 | 확정에 필요한 값 누락 |
| `CLUB_ACCESS_PENDING` | 403 | 대표 허가 대기 중 |
| `CONVERSATION_NOT_FOUND` | 404 | |
| `STEP_ALREADY_COMPLETED` | 409 | 이미 완료 처리된 단계에 완료 API 호출 |

검증 실패일 때만 `fields`가 붙습니다.

```jsonc
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "입력을 확인해 주세요.",
    "fields": { "startDate": "종료일보다 빠를 수 없습니다." }
  }
}
```

---

# 1. 행사 계획 (P1 · P2)

v5에서 계획이 2단계로 통합되었습니다.

| 단계 | 화면 | 하는 일 |
| --- | --- | --- |
| 1단계 | P1 | 챗봇 대화로 행사 조건(유형·일정·인원·예산·장소)을 잡음 |
| 2단계 | P2 | AI가 만든 7단계 흐름을 확인·수정하고 확정 |

Event 행은 1단계 시작 시 `status=PLANNING`으로 생성되고, 확정 시 같은 행이 `ON_GOING`으로 바뀝니다. 새 행이 생기지 않습니다.

---

## GET /events/drafts

임시 저장한 계획 목록입니다. P1 우측 "임시 저장한 계획" 카드를 그립니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P1 우측 패널 |
| 비고 | `status=PLANNING`이고 `saved_at`이 있는 Event만 |

> ⚠️ **라우팅 주의** — `/events/drafts`가 `/events/{eventId}`보다 **먼저** 등록돼야 합니다.
> 순서가 반대면 `drafts`가 eventId로 해석돼 `EVENT_NOT_FOUND`가 납니다.
>
> `GET /events?status=PLANNING`과 대상이 겹치지만 용도가 다릅니다.
> L1 "계획 중" 카드는 후자를, P1 우측 패널은 `conversationId`와 `stage`가 필요해 이쪽을 씁니다.
> 하나로 합치자는 의견이 있으면 `GET /events?status=PLANNING&include=conversation` 형태도 가능합니다.

```
GET /api/v1/events/drafts?clubId=clb_3a71c0
```

**응답 — data[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | |
| `title` | string | 대화 생성 시 정해지므로 항상 존재 |
| `stage` | enum | `CHAT` / `FLOW` — 어느 단계에서 멈췄는지. 서버 계산값 |
| `savedAt` | datetime | "3/2 저장" |
| `conversationId` | string | 이어서 하기 시 대화 로드용. 🔸 Event:Conversation이 1:N이라 **계획용 대화를 특정하는 규칙 필요** (가장 최근 것으로 가정) |

```jsonc
{
  "data": [
    { "id": "evt_5c11a2", "title": "여름 워크샵", "stage": "CHAT", "savedAt": "2026-03-02T11:40:00Z", "conversationId": "cnv_88ae01" },
    { "id": "evt_7b02f4", "title": "가을 체육대회", "stage": "FLOW", "savedAt": "2026-02-28T09:02:00Z", "conversationId": "cnv_12cc33" }
  ],
  "meta": null
}
```

> `stage`는 컬럼이 아니라 서버 계산값입니다. Step이 0개면 `CHAT`, 1개 이상이면 `FLOW`.

---

## GET /conversations/{conversationId}/messages

대화 이력을 불러옵니다. 임시 저장한 계획을 "이어서 하기" 할 때 호출합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P1 "이어서 하기" |

```
GET /api/v1/conversations/cnv_88ae01/messages
```

**응답**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `conversationId` | string | |
| `eventId` | string | |
| `messages` | array | 시간순. `SYSTEM`은 제외하고 내려줌 |
| `collected` | object | 우측 "지금까지 정해진 것" 복원용 |
| `readyToGenerate` | boolean | |

```jsonc
{
  "data": {
    "conversationId": "cnv_88ae01",
    "eventId": "evt_5c11a2",
    "messages": [
      { "id": "msg_01", "role": "ASSISTANT", "content": "어떤 행사를 준비하시나요?", "createdAt": "2026-03-02T11:00:00Z" },
      { "id": "msg_02", "role": "USER", "content": "여름 워크샵이요.", "createdAt": "2026-03-02T11:01:00Z" }
    ],
    "collected": { "eventType": "WORKSHOP", "startDate": null, "endDate": null },
    "readyToGenerate": false
  },
  "meta": null
}
```

---

## POST /events

새 행사 계획을 시작합니다. Event(`status=PLANNING`)와 Conversation을 함께 만들고, 챗봇 첫 인사 메시지까지 반환합니다.
`Conversation.member_id`는 토큰의 사용자로 채웁니다.

**`title`은 이 시점에 반드시 정해집니다.** 임시 저장 목록에서 구분하려면 제목이 있어야 하므로, 사용자가 직접 입력하거나 비워두면 서버가 기본값(`새 행사 · 3월 2일`)을 넣습니다.

> 🔸 현재 스키마의 `events.title`은 `nullable=True`입니다. **`nullable=False`로 변경을 요청했습니다.**

> 대화 관련 호출은 모두 `conversationId` 기준입니다. `eventId`로 대화에 접근하지 않습니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L1 "+ 새 행사 계획하기", P1 진입 |
| 권한 | `OWNER` / `MANAGER` |
| 성공 | 201 |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `clubId` | string | ✓ | 소속 동아리 |
| `title` | string | | 생략 시 서버가 기본값 부여 |

```jsonc
// 요청
{ "clubId": "clb_3a71c0", "title": "봄 MT" }
```

**응답**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | `evt_` 접두 |
| `title` | string | 항상 존재 |
| `status` | enum | 항상 `PLANNING` |
| `conversationId` | string | 1단계 대화 세션 |
| `messages` | array | 첫 인사 메시지 1건 |

```jsonc
{
  "data": {
    "id": "evt_9f2c8a",
    "title": "봄 MT",
    "status": "PLANNING",
    "conversationId": "cnv_41b7d9",
    "messages": [
      { "id": "msg_01", "role": "ASSISTANT", "content": "어떤 행사를 준비하시나요?", "createdAt": "2026-03-01T04:12:00Z" }
    ]
  },
  "meta": null
}
```

---

## POST /conversations/{conversationId}/messages

1단계 챗봇에 메시지를 보냅니다. 대화 이력은 `Conversation` / `Message`에 저장됩니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P1 하단 챗봇 바 |
| 비고 | AI 호출은 `AgentLog(feature=PLANNING)`에 기록 |
| 실패 | `CONVERSATION_NOT_FOUND` (404) |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `content` | string | ✓ | 사용자 발화 |

```jsonc
// 요청
{ "content": "봄 MT요. 3월 셋째 주 주말에 1박 2일로 생각하고 있어요." }
```

**응답**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `message` | object | AI 응답 메시지 |
| `collected` | object | 지금까지 확정된 조건 (P1 우측 패널) |
| `readyToGenerate` | boolean | 2단계로 넘어갈 수 있는지 |

```jsonc
{
  "data": {
    "message": {
      "id": "msg_07", "role": "ASSISTANT",
      "content": "정리했습니다. 이대로 다음 단계로 넘어갈까요?",
      "createdAt": "2026-03-01T04:20:00Z"
    },
    "collected": {
      "eventType": "MT",
      "startDate": "2026-03-21",
      "endDate": "2026-03-22",
      "headcount": 32,          // 🔸 events.expected_headcount 추가 필요
      "budgetTotal": 2000000,   // 🔸 events.budget_total 추가 필요
      "locationCandidates": ["가평", "양평"]  // 🔸 저장 위치 미정
    },
    "readyToGenerate": true
  },
  "meta": null
}
```

> 🔸 `collected`의 값 중 `headcount` / `budgetTotal` / `locationCandidates`를 담을 컬럼이 아직 없습니다.
> 임시로 응답에만 포함하고 DB에는 저장하지 않거나, `events`에 컬럼을 추가해야 합니다.

---

## POST /events/{eventId}/plan:generate

1단계 대화를 근거로 AI가 단계(Step)와 행동(Action)을 생성합니다. 기존 Step·Action이 있으면 전부 교체합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P1 "다음 단계로" → P2 진입 |
| 실패 | `EVENT_NOT_PLANNING` (이미 확정된 행사) |
| 비고 | 응답이 수십 초 걸릴 수 있음. 로딩 처리 필요 |
| 경로 표기 | `:generate` 같은 콜론 표기는 **팀 합의 필요**. `/plan/generate` 로 바꿔도 무방 |

**요청** — 본문 없음. 1단계 대화(`Conversation`)를 서버가 직접 읽습니다.

```jsonc
// 요청
{}
```

**응답** — `GET /events/{eventId}/plan`과 동일 구조 (아래 참고)

---

## GET /events/{eventId}/plan

2단계 화면 전체를 그리는 데이터입니다. 단계 목록, 각 단계의 행동, 우측 요약이 한 번에 내려옵니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P2 진입 / 새로고침 |

```
GET /api/v1/events/evt_9f2c8a/plan
```

**응답 — 최상위**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `eventId` | string | |
| `title` | string | `POST /events` 시점에 정해지므로 항상 존재 |
| `phases` | array | 묶음. `steps.phase` 기준으로 서버가 그룹핑 |
| `summary` | object | 우측 "이 계획 요약" |
| `warnings` | array | "시작 전에 확인하세요". §"warnings 형식" 참고 (v1에서 구조 변경) |
| `excludedSteps` | array | "13단계에서 어디로 갔나" 목록 |

**phases[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `phase` | enum | `PREPARATION` / `RECRUITING` / `EXECUTION` |
| `name` | string | "사전 준비" |
| `description` | string | "인원과 예산의 윤곽을 잡습니다" — 🔸 저장 위치 미정. 코드 상수로 둬도 됨 |
| `steps` | array | 하위 단계 |

**steps[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | `stp_` |
| `stepOrder` | int | 정렬 기준 |
| `phase` | enum | 🔸 `PREPARATION` / `RECRUITING` / `EXECUTION` |
| `name` | string | "사전 수요 조사" |
| `actor` | enum | 블록 색 결정 (`AI`/`APPROVAL_REQUIRED`/`MANUAL`) |
| `startedTime` | datetime \| null | 예정 시작 |
| `deadline` | datetime \| null | 예정 마감 |
| `actions` | array | 이 단계의 행동 |

**actions[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | `act_` |
| `type` | enum | `NOTICE` 등. P2의 "공지"·"수금" 배지 |
| `title` | string | |
| `subtitle` | string \| null | 설명 문단 |
| `irreversible` | boolean | 사실 |
| `approveNeeded` | boolean | 정책 판정 |
| `amount` | int \| null | 🔸 `actions.amount` 추가 필요 |

**summary**

| 필드 | 타입 | 예시 |
| --- | --- | --- |
| `totalSteps` | int | 7 |
| `countByActor` | object | `{ "AI": 3, "APPROVAL_REQUIRED": 3, "MANUAL": 1 }` |
| `collectionPlan` | object \| null | 🔸 `{ "times": 1, "feePerPerson": 45000 }` |
| `noticeCount` | int | 2 |
| `periodStart` / `periodEnd` | date | |

### `warnings` 형식 (v1에서 변경)

`RULE`(규칙 기반)과 `AI`(모델이 짚은 것)를 만든 주체로 나눕니다. 전부 `code`로 강제하면 예상 못 한 문제를 짚는 AI 경고가 막히기 때문입니다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `source` | enum | `RULE` \| `AI` |
| `code` | string | `source=RULE`일 때만. `services/event_rules.py`가 만드는 유한 목록 |
| `params` | object | `source=RULE`일 때만. 문구 조립에 쓰는 값 |
| `suggestion` | string | `source=RULE`일 때만 |
| `message` | string | `source=AI`일 때만. 자유 문장, 그대로 표시 |
| `debugMessage` | string | `source=RULE`일 때 폴백용. FE가 모르는 `code`면 이 문구를 대신 씁니다 |

규칙 경고 `code` 초안: `SCHEDULE_GAP` / `BUDGET_EXCEEDED` / `PREP_TIME_SHORT` / `SCHEDULE_CONFLICT` / `MINIMUM_HEADCOUNT_VIOLATED` (파서 구현 시 확정, 추가만 가능)

```jsonc
{
  "data": {
    "eventId": "evt_9f2c8a",
    "title": "2026 봄 MT",
    "phases": [
      {
        "phase": "PREPARATION",
        "name": "사전 준비",
        "description": "인원과 예산의 윤곽을 잡습니다",
        "steps": [
          {
            "id": "stp_01", "stepOrder": 10, "phase": "PREPARATION", "name": "사전 수요 조사",
            "actor": "APPROVAL_REQUIRED",
            "startedTime": "2026-03-05T00:00:00Z", "deadline": null,
            "actions": [
              {
                "id": "act_01", "type": "NOTICE",
                "title": "수요조사 폼 발송",
                "subtitle": "수요조사 폼을 만들어 단톡방에 올립니다. 폼 생성은 자동, 발송 직전 승인 한 번.",
                "irreversible": true, "approveNeeded": true,
                "amount": null
              }
            ]
          }
        ]
      }
    ],
    "summary": {
      "totalSteps": 7,
      "countByActor": { "AI": 3, "APPROVAL_REQUIRED": 3, "MANUAL": 1 },
      "collectionPlan": { "times": 1, "feePerPerson": 45000 },
      "noticeCount": 2,
      "periodStart": "2026-03-02",
      "periodEnd": "2026-03-25"
    },
    "warnings": [
      {
        "source": "RULE", "code": "SCHEDULE_GAP",
        "params": { "fromStep": "입금 마감", "fromDate": "2026-03-12",
                    "toStep": "리허설", "toDate": "2026-03-20", "gapDays": 8 },
        "suggestion": "ADD_CHECKPOINT", "debugMessage": "입금 마감과 리허설 사이 8일 공백"
      },
      {
        "source": "AI",
        "message": "작년 MT는 32명이었는데 올해 40명이면 버스 한 대로 부족합니다."
      }
    ],
    "excludedSteps": [
      { "name": "일정 확정", "reason": "세부사항 조정에 포함" },
      { "name": "리허설", "reason": "MT 특성상 없음" }
    ]
  },
  "meta": null
}
```

> 🔸 `warnings` / `excludedSteps`를 담을 컬럼이 없습니다. `plan:generate` 때만 만들어지고 새로고침하면 사라집니다.
> `events`에 JSONB 컬럼(`plan_meta`)을 하나 두는 방안을 제안합니다. **BE 확인 필요.**

---

## PATCH /events/{eventId}/steps/{stepId}

단계의 이름·일정을 수정합니다. P2의 각 단계 "수정" 링크입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P2 단계별 "수정" |

**요청** — 모두 선택, 보낸 필드만 갱신

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `name` | string | |
| `startedTime` | datetime \| null | |
| `deadline` | datetime \| null | |

```jsonc
// 요청 — 마감일만 바꾸는 경우
{ "deadline": "2026-03-14T14:59:00Z" }

// 요청 — 이름과 일정을 함께
{
  "name": "입금 내역 확인 및 미납 정리",
  "startedTime": "2026-03-10T00:00:00Z",
  "deadline": "2026-03-14T14:59:00Z"
}
```

```jsonc
// 응답 — 갱신된 단계 단건
{
  "data": {
    "id": "stp_03", "stepOrder": 30,
    "name": "입금 내역 확인 및 미납 정리",
    "actor": "AI",
    "startedTime": "2026-03-10T00:00:00Z",
    "deadline": "2026-03-14T14:59:00Z"
  },
  "meta": null
}
```

---

## PATCH /events/{eventId}/steps:reorder

단계 순서를 한 번에 재배열합니다.

> **v1 변경** — `steps.phase`가 생겨 단계를 다른 묶음으로 옮기는 이동을 표현해야 합니다.
> `stepIds` 배열만으로는 순서만 바뀌고 묶음(phase) 이동을 나타낼 수 없어, 각 항목에 `phase`를 함께 보냅니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P2 블록 드래그 |
| 비고 | `uq_steps_event_order` 충돌을 피하려고 **전체를 한 트랜잭션으로 교체**. 개별 PATCH 금지 |

**요청**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `steps` | array | 새 순서대로 나열한 전체 단계. 각 항목은 `{ stepId, phase }` |
| `steps[].stepId` | string | |
| `steps[].phase` | enum | 이동 후 소속 묶음 |

```jsonc
// 요청
{
  "steps": [
    { "stepId": "stp_02", "phase": "PREPARATION" },
    { "stepId": "stp_01", "phase": "PREPARATION" },
    { "stepId": "stp_03", "phase": "RECRUITING" },
    { "stepId": "stp_04", "phase": "RECRUITING" },
    { "stepId": "stp_05", "phase": "RECRUITING" },
    { "stepId": "stp_06", "phase": "EXECUTION" },
    { "stepId": "stp_07", "phase": "EXECUTION" }
  ]
}
```

```jsonc
// 응답 — 재부여된 순서
{
  "data": [
    { "id": "stp_02", "stepOrder": 10, "phase": "PREPARATION", "name": "세부사항 조정" },
    { "id": "stp_01", "stepOrder": 20, "phase": "PREPARATION", "name": "사전 수요 조사" }
  ],
  "meta": null
}
```

> `stepOrder`는 서버가 10·20·30… 으로 다시 부여합니다. 배열 순서 자체가 새 `step_order`를 의미합니다.

---

## PATCH /events/{eventId}

계획 임시 저장. `saved_at`을 갱신합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P1 · P2 "임시 저장" |

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `title` | string | 제목 변경 |
| `startDate` | date | |
| `endDate` | date | 🔸 `events.end_date` 추가 필요 |
| `budgetTotal` | int | 🔸 컬럼 추가 필요 |
| `feePerPerson` | int | 🔸 컬럼 추가 필요 |
| `headcount` | int | 🔸 컬럼 추가 필요. v1: `expectedHeadcount`에서 `headcount`로 통일 (`GET /events/{id}` 등 다른 응답과 이름을 맞춤) |

```jsonc
// 요청 — 보낸 필드만 갱신
{
  "title": "2026 봄 MT",
  "startDate": "2026-03-21",
  "endDate": "2026-03-22",     // 🔸
  "budgetTotal": 1940000,      // 🔸
  "feePerPerson": 45000,       // 🔸
  "headcount": 32              // 🔸
}
```

```jsonc
// 응답
{
  "data": {
    "id": "evt_9f2c8a",
    "title": "2026 봄 MT",
    "status": "PLANNING",
    "startDate": "2026-03-21",
    "savedAt": "2026-03-02T11:40:00Z"
  },
  "meta": null
}
```

---

## POST /events/{eventId}:confirm

계획을 확정합니다. `status`가 `PLANNING` → `ON_GOING`으로 바뀌고 첫 단계가 시작됩니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | P2 "이 계획으로 행사 시작하기" |
| 권한 | `OWNER` / `MANAGER` |
| 실패 | `PLAN_INCOMPLETE` — `startDate` 미입력, 또는 Step이 0개일 때 |

**요청** — 본문 없음

```jsonc
// 요청
{}
```

**응답**

```jsonc
{ "data": { "id": "evt_9f2c8a", "status": "ON_GOING", "title": "2026 봄 MT", "startDate": "2026-03-21" }, "meta": null }
```

---

# 2. 행사 목록 (L1)

## GET /events

행사 목록입니다. 상태별로 필터링합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L1 "진행 중인 행사" / "계획 중" / "끝난 행사" |

**요청 쿼리**

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `clubId` | string | — | 필수 |
| `status` | enum | 전체 | `PLANNING` / `ON_GOING` / `COMPLETE` |
| `page` / `size` | int | 1 / 20 | |

```
GET /api/v1/events?clubId=clb_3a71c0&status=ON_GOING&page=1&size=20
```

**응답 — data[]**

| 필드 | 타입 | 설명 | 화면 |
| --- | --- | --- | --- |
| `id` | string | | |
| `title` | string \| null | | 카드 제목 |
| `status` | enum | | |
| `startDate` / `endDate` | date \| null | | "3/21–3/22" |
| `dday` | int \| null | | "D-11" |
| `currentStepName` | string \| null | | "수납 단계" 배지 |
| `stepProgress` | array | 단계별 완료 상태 | 미니 진행 바 |
| `pendingApprovalCount` | int | `ActionStatus=PENDING` 개수 | "승인 대기 3건" |
| `payment` | object \| null | 🔸 | "32명 중 28명 납부" |
| `budget` | object \| null | 🔸 | "1,940,000원 중 588,000원 집행" |

```jsonc
{
  "data": [
    {
      "id": "evt_9f2c8a",
      "title": "2026 봄 MT",
      "status": "ON_GOING",
      "startDate": "2026-03-21", "endDate": "2026-03-22",
      "dday": 11,
      "currentStepName": "수납",
      "stepProgress": [
        { "stepOrder": 10, "state": "DONE" },
        { "stepOrder": 20, "state": "DONE" },
        { "stepOrder": 30, "state": "CURRENT" },
        { "stepOrder": 40, "state": "TODO" }
      ],
      "pendingApprovalCount": 3,
      "payment": null,  // 🔸 participants + transactions 확정 후
      "budget": null    // 🔸 transactions + events.budget_total 확정 후
    }
  ],
  "meta": { "page": 1, "size": 20, "totalCount": 3 }
}
```

> 🔸 `payment` / `budget`은 스키마 확정 후 아래 형태로 채웁니다. **필드 자리는 지금 잡아둡니다.**
> `payment: { "paidCount": 28, "totalCount": 32, "collected": 1260000, "target": 1440000 }`
> `budget: { "spent": 588000, "planned": 1940000 }`

---

# 3. 행사 상세 (L2)

## GET /events/{eventId}

행사 상세 상단(제목·상태·기간)과 요약입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L2 헤더 |

```
GET /api/v1/events/evt_9f2c8a
```

**응답**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` / `title` / `status` | | |
| `startDate` / `endDate` / `dday` | | "3/21–3/22 · 출발까지 11일" |
| `location` | string \| null | 🔸 저장 위치 미정 ("가평 ○○펜션") |
| `headcount` | int \| null | 🔸 `expected_headcount` 필요 |
| `currentStep` | object | `{ id, stepOrder, name }` |
| `payment` / `budget` | object \| null | 🔸 위와 동일 |

```jsonc
// 응답
{
  "data": {
    "id": "evt_9f2c8a",
    "title": "2026 봄 MT",
    "status": "ON_GOING",
    "startDate": "2026-03-21", "endDate": "2026-03-22", "dday": 11,
    "location": null,      // 🔸
    "headcount": null,     // 🔸
    "currentStep": { "id": "stp_03", "stepOrder": 30, "name": "입금 내역 확인" },
    "payment": null,       // 🔸
    "budget": null         // 🔸
  },
  "meta": null
}
```

---

## GET /events/{eventId}/steps

진행 상황 그래프와 단계 상세입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L2 "진행 상황" 카드 |

```
GET /api/v1/events/evt_9f2c8a/steps
```

**응답 — data[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` / `stepOrder` / `name` | | |
| `actor` | enum | 막대 색 |
| `state` | enum | `DONE` / `CURRENT` / `TODO` (서버 계산) |
| `startedTime` / `deadline` | datetime \| null | "3/10 – 3/12" |
| `completedCount` / `totalActionCount` | int | 이 단계 Action 중 `DONE` 개수 / 전체 개수 (진행률 계산용, `completedAt`과는 별개) |
| `completedAt` | datetime \| null | 완료 판정 시각. v1에서 신설 |
| `doneActions` | array | 펼쳤을 때 "이 단계에서 한 일" |
| `remainingActions` | array | "남은 일" |

```jsonc
{
  "data": [
    {
      "id": "stp_03", "stepOrder": 30, "name": "입금 내역 확인",
      "actor": "AI", "state": "CURRENT",
      "startedTime": "2026-03-10T00:00:00Z", "deadline": "2026-03-12T14:59:00Z",
      "completedCount": 3, "totalActionCount": 4,
      "completedAt": null,
      "doneActions": [
        { "id": "act_11", "title": "입금 12건을 참가자 명단과 대조했습니다", "status": "DONE" }
      ],
      "remainingActions": [
        { "id": "act_14", "title": "미납자 4명에게 2차 안내 발송", "status": "PENDING", "approveNeeded": true }
      ]
    }
  ],
  "meta": null
}
```

> ⚠️ **완료 표시와 진행률은 어긋날 수 있습니다.** 완료 판정은 `completedAt` 기준, 진행률은 Action 개수 기준이라
> `[✓ 완료] 입금 확인 2/4` 같은 상태가 정상적으로 발생합니다. 완료된 단계는 진행률 막대를 숨기거나
> "4개 중 2개 처리 · 완료됨"처럼 문구를 구분해 표시합니다. **화면 결정은 FE 몫입니다.**

---

## POST /steps/{stepId}/complete (v1 신설)

MANUAL 단계처럼 Action이 없거나, Action이 일부 `FAILED`로 끝나 자동으로는 완료되지 않는 단계를 사람이 직접 완료 처리합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L2 "진행 상황" 카드의 단계별 "완료 처리" |
| 권한 | `OWNER` / `MANAGER` |
| 실패 | `STEP_ALREADY_COMPLETED` (409) — 이미 `completedAt`이 있는 단계 |

**요청** — 본문 없음. `completedBy`는 토큰의 사용자로 서버가 채웁니다.

```jsonc
// 요청
{}
```

**응답** — 갱신된 step + 처리 시점의 미처리 Action 수

```jsonc
{
  "data": {
    "id": "stp_03",
    "completedAt": "2026-03-12T09:10:00Z",
    "completedBy": { "id": "mbr_01", "name": "박수겸", "role": "MANAGER" },
    "pendingActionCount": 1
  },
  "meta": null
}
```

**동작 규칙**

- 서버는 그 단계의 Action이 모두 `DONE`이 되는 순간 자동으로도 `completedAt`을 채웁니다(이때 `completedBy`는 `null`). 이 API는 그 외의 경우 — Action이 `FAILED`로 끝나 총무가 오프라인으로 처리했거나, Action이 아예 없는 MANUAL 단계 — 를 위한 것입니다.
- **미처리(`PENDING`/`APPROVED`) Action이 남아 있어도 완료할 수 있습니다.** 거부하면 승인 대기 중인 행동을 오프라인으로 처리한 경우 완료할 방법이 없어집니다. 응답의 `pendingActionCount`를 보고 "미처리 N건이 남아 있습니다. 완료하시겠습니까?" 확인은 **FE가 처리**합니다.
- 이미 `completedAt`이 있는 단계를 다시 호출하면 `STEP_ALREADY_COMPLETED` (409). 최초 완료 시점·처리자를 덮어쓰지 않습니다.
- 되돌리기(`:reopen`)는 없습니다. 필요해지면 나중에 추가해도 `completedAt`을 `null`로 되돌리는 것뿐이라 마이그레이션 부담이 없습니다.

---

## GET /events/{eventId}/actions

승인 대기 / 처리된 승인 / 확인 요청을 모두 이 엔드포인트로 조회합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L2 "확인 요청", "처리된 승인" / M1 "승인 대기" |

**요청 쿼리**

| 파라미터 | 값 | 화면 |
| --- | --- | --- |
| `status` | `PENDING` | 승인 대기 |
| | `APPROVED,DONE,DENIED` | "처리된 승인" 탭. `DONE`을 빠뜨리면 실행까지 끝난 건이 목록에서 사라짐 |
| `type` | `CONFIRMATION` | "확인 요청" 카드 |
| `excludeType` | `CONFIRMATION` | 확인 요청을 뺀 일반 승인 |
| `page` / `size` | int | |

> ⚠️ `excludeType`은 **FE에서 임의로 제안한 파라미터**입니다. 확인 요청과 일반 승인이 같은 테이블에 있어서 "포함"과 "제외"가 모두 필요한데, `type` 하나로는 표현이 안 됩니다. BE에서 다른 방식을 원하면 알려주세요.

```
// 승인 대기 (M1, 확인 요청 제외)
GET /api/v1/events/evt_9f2c8a/actions?status=PENDING&excludeType=CONFIRMATION

// 확인 요청 (L2)
GET /api/v1/events/evt_9f2c8a/actions?status=PENDING&type=CONFIRMATION

// 처리된 승인 (L2)
GET /api/v1/events/evt_9f2c8a/actions?status=APPROVED,DONE,DENIED&page=1&size=5
```

**응답 — data[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` / `type` / `title` / `subtitle` | | |
| `irreversible` / `approveNeeded` | boolean | 배지 |
| `status` | enum | |
| `amount` | int \| null | 🔸 `actions.amount` 필요 |
| `dueDate` | date \| null | |
| `stepId` / `stepName` | | 어느 단계 소속인지 |
| `resolvedAt` | datetime \| null | 처리 시각 (v1: `approvedAt`에서 개명) |
| `resolvedBy` | object \| null | `{ id, name, role }` — 처리자 (v1: `approvedBy`에서 개명) |
| `denyReason` | string \| null | 🔸 **컬럼 없음.** 거절 사유 표시하려면 추가 필요 |
| `canApprove` | boolean | 요청자 권한으로 처리 가능한지 (`meta`가 아닌 항목별) |

> **v1 변경** — `approvedAt`/`approvedBy`는 승인뿐 아니라 거절·확인요청 처리도 같은 필드로 받습니다.
> "승인됨"만을 뜻하는 이름이라 혼동이 있어 `resolvedAt`/`resolvedBy`로 통일합니다.

```jsonc
{
  "data": [
    {
      "id": "act_21", "type": "EXTERNAL_SEND",
      "title": "미납자 4명에게 2차 납부 안내 문자 발송",
      "subtitle": "대상 4명 · 비용 0원 · 마감 D-2",
      "irreversible": true, "approveNeeded": true,
      "status": "PENDING",
      "amount": null,
      "dueDate": "2026-03-12",
      "stepId": "stp_03", "stepName": "입금 내역 확인",
      "resolvedAt": null, "resolvedBy": null, "denyReason": null,
      "canApprove": true
    },
    {
      "id": "act_09", "type": "CONTRACT",
      "title": "버스 대절 업체 B와 계약",
      "subtitle": null,
      "irreversible": true, "approveNeeded": true,
      "status": "DENIED",
      "amount": null,
      "dueDate": null,
      "stepId": "stp_02", "stepName": "세부사항 조정",
      "resolvedAt": "2026-03-08T08:02:00Z",
      "resolvedBy": { "id": "mbr_01", "name": "박수겸", "role": "MANAGER" },
      "denyReason": "견적이 작년보다 40% 높아 다른 업체를 더 받아보기로 했습니다.",
      "canApprove": true
    }
  ],
  "meta": { "page": 1, "size": 20, "totalCount": 12 }
}
```

> 🔸 `denyReason`을 담을 컬럼이 `actions`에 없습니다. L2 "처리된 승인"에서 거절 사유를 보여주기로 했으므로 **컬럼 추가가 필요합니다.**

---

## POST /actions/{actionId}/approve

승인합니다. `status`가 `APPROVED`로 바뀌고 `resolved_by` / `resolved_at`이 기록됩니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | M1 "승인", L2 확인 요청 "맞아요" |
| 권한 | `OWNER` / `MANAGER` |
| 실패 | `ALREADY_RESOLVED` (409) — 다른 임원이 먼저 처리한 경우 |

**요청** — 본문 없음

```jsonc
// 요청
{}
```

**응답** — 갱신된 Action 단건

```jsonc
{
  "data": {
    "id": "act_21",
    "status": "APPROVED",
    "resolvedAt": "2026-03-10T05:31:00Z",
    "resolvedBy": { "id": "mbr_01", "name": "박수겸", "role": "MANAGER" }
  },
  "meta": null
}
```

> 응답은 `APPROVED`입니다. 실제 실행은 Agent가 비동기로 하며, 끝나면 `DONE`으로 바뀝니다.
> 프론트는 승인 직후 `APPROVED` 상태로 표시하고, 목록을 다시 불러올 때 `DONE`으로 갱신합니다.
>
> 동시 처리 대응: 409를 받으면 프론트는 목록을 다시 불러옵니다.

---

## POST /actions/{actionId}/deny

거절합니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | M1 "아니에요", L2 확인 요청 "아니에요" |
| 권한 | `OWNER` / `MANAGER` |
| 실패 | `ALREADY_RESOLVED` (409) — 다른 임원이 먼저 처리한 경우 |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reason` | string | ? | 🔸 저장 컬럼 없음. 필수 여부도 미정 |

```jsonc
// 요청
{ "reason": "견적이 작년보다 40% 높아 다른 업체를 더 받아보기로 했습니다." }
```

```jsonc
// 응답
{
  "data": {
    "id": "act_09",
    "status": "DENIED",
    "resolvedAt": "2026-03-08T08:02:00Z",
    "resolvedBy": { "id": "mbr_01", "name": "박수겸", "role": "MANAGER" },
    "denyReason": "견적이 작년보다 40% 높아 다른 업체를 더 받아보기로 했습니다."
  },
  "meta": null
}
```

---

## POST /actions/{actionId}/resolve

확인 요청(`type=CONFIRMATION`)을 처리합니다. 승인·거절이 아니라 **선택지 중 하나를 고르는** 것이라 별도 엔드포인트입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | L2 확인 요청 카드의 선택 버튼 / "직접 처리" |
| 실패 | `ALREADY_RESOLVED` (409) |

확인 요청은 조회 시 선택지를 함께 내려줍니다.

```jsonc
// GET /events/{id}/actions?type=CONFIRMATION 응답 中
{
  "id": "act_31", "type": "CONFIRMATION",
  "title": "어느 행사인지 모르겠습니다",
  "subtitle": "학생회 지원금 500,000원 — 봄 MT에 넣을까요, 공동 회계로 둘까요?",
  "status": "PENDING",
  "options": [
    { "key": "ASSIGN_EVENT", "label": "봄 MT에 넣기" },
    { "key": "ASSIGN_CLUB",  "label": "공동 회계로" }
  ],
  "allowManual": true
}
```

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `choice` | string | ✓ | `options[].key` 중 하나, 또는 `MANUAL` |
| `manualValue` | object | | `choice=MANUAL`일 때 사용자가 직접 입력한 값 |

```jsonc
// 요청 — 선택지 중 하나
{ "choice": "ASSIGN_EVENT" }

// 요청 — 직접 처리
{ "choice": "MANUAL", "manualValue": { "memberId": "mbr_42" } }
```

```jsonc
// 응답
{
  "data": { "id": "act_31", "status": "DONE", "resolvedChoice": "ASSIGN_EVENT" },
  "meta": null
}
```

> 🔸 `options` / `allowManual` / `resolvedChoice`를 담을 컬럼이 없습니다.
> `actions`에 JSONB 컬럼(`payload`)을 두고 확인 요청의 선택지·처리 결과를 담는 방안을 제안합니다. **BE 확인 필요.**
> 미루기는 별도 선택지를 두지 않습니다. 처리하지 않고 화면을 벗어나면 `PENDING`으로 남습니다.

---

## ⏸ GET /events/{eventId}/budget

예산 현황. **정의 보류.**
대기 중: `transactions` 테이블, `events.budget_total` 컬럼

## ⏸ GET /events/{eventId}/payments

수납 현황·미납·환불 목록. **정의 보류.**
대기 중: `transactions`, `participants` 테이블

---

# 4. 동아리 기록 (R1)

금액과 무관하여 **전 구간 구현 가능합니다.**

## GET /records

카테고리별 파일 목록입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | R1 4개 카테고리 카드 |

**요청 쿼리**

| 파라미터 | 타입 | 설명 |
| --- | --- | --- |
| `clubId` | string | 필수 |
| `category` | enum | 생략 시 전체 |
| `eventId` | string | 특정 행사 자료만 |

> **페이지네이션 없이 전체를 반환합니다.** 동아리 하나가 가진 문서가 수십 건 수준이라 나눌 이유가 없고,
> R1은 4개 카테고리를 한 화면에 펼쳐 보여주므로 부분 조회가 오히려 화면과 안 맞습니다.

```
GET /api/v1/records?clubId=clb_3a71c0
```

**응답 — data[]**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | string | `rec_` |
| `fileName` | string | |
| `fileType` | enum | |
| `category` | enum | |
| `size` | int | bytes |
| `parseStatus` | enum | 상태 칩 |
| `createdAt` | datetime | "2026. 3. 1." |

**meta**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `totalCount` | int | "총 25건" |
| `categoryCounts` | object | 각 카테고리 헤더의 "3건", "8건" |
| `indexedCount` | int | "AI가 읽은 문서 22건" |

> 페이지네이션이 없으므로 `page` / `size`는 내려주지 않습니다.

```jsonc
{
  "data": [
    {
      "id": "rec_01", "fileName": "동아리 회칙 (2024 개정).pdf",
      "fileType": "PDF", "category": "PLAN", "size": 482301,
      "parseStatus": "INDEXED", "createdAt": "2026-03-01T02:00:00Z"
    },
    {
      "id": "rec_09", "fileName": "2024 하반기 장부.csv",
      "fileType": "CSV", "category": "LEDGER", "size": 20114,
      "parseStatus": "NEEDS_REVIEW", "createdAt": "2026-02-28T05:00:00Z"
    }
  ],
  "meta": {
    "totalCount": 25,
    "categoryCounts": { "PLAN": 3, "NOTICE": 8, "LEDGER": 12, "ETC": 2 },
    "indexedCount": 22
  }
}
```

---

## GET /records/{recordId}

파일 단건. **`parseError`를 포함합니다.** R1의 "왜 못 읽었나" 박스를 그리는 데이터입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | R1 파일 행 펼침 |

```
GET /api/v1/records/rec_09
```

**parseError 형식 (JSONB)** — v1: BE 확정안 반영

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `reason` | enum | `COLUMN_MISMATCH` / `IMAGE_NOT_READABLE` / `UNSUPPORTED_FORMAT` / `UNKNOWN`(v1 추가) |
| `params` | object | 원인별 부가 정보. 예: 열 불일치면 `expectedColumns`/`actualColumns` |
| `debugMessage` | string | 로그용 원문. **화면에 노출하지 않음** |

> **v1 변경** — `detail`(서버가 만든 문장) 필드를 없앴습니다. 프로젝트 공통 규칙("서버 message를 화면에 그대로 노출하지 않는다")에 맞춰,
> 화면 문구는 FE가 `reason` 코드를 보고 매핑합니다. `expectedColumns`/`actualColumns`는 `params` 객체 안으로 이동했습니다.
> `suggestions`는 DB에 저장하지 않고 `reason`에서 FE가 유도합니다 (예: `COLUMN_MISMATCH` → "열 직접 맞추기" 버튼).
> **FE는 모르는 `reason` 값을 받으면 `UNKNOWN`으로 취급**해야 합니다. 값 목록은 파서 구현 시 확정되며 이후로도 추가만 됩니다.

```jsonc
{
  "data": {
    "id": "rec_09", "fileName": "2024 하반기 장부.csv",
    "fileType": "CSV", "category": "LEDGER",
    "parseStatus": "NEEDS_REVIEW",
    "parseResult": null,
    "parseError": {
      "reason": "COLUMN_MISMATCH",
      "params": {
        "expectedColumns": ["날짜", "적요", "입금", "출금"],
        "actualColumns": ["일자", "내용", "금액", "구분"]
      },
      "debugMessage": "열 이름이 표준과 달라 어떤 값이 금액인지 찾지 못했습니다."
    },
    "createdAt": "2026-02-28T05:00:00Z"
  },
  "meta": null
}
```

> FE 문구/버튼 매핑 예시 (`reason` 기준):
> - `COLUMN_MISMATCH` → "열 이름이 표준과 달라 어떤 값이 금액인지 찾지 못했습니다." + [열 직접 맞추기] [양식 받아서 다시 만들기]
> - `IMAGE_NOT_READABLE` → "이미지를 읽지 못했습니다." + [다시 올리기]
> - `UNSUPPORTED_FORMAT` → "지원하지 않는 파일 형식입니다."
> - `UNKNOWN` → "원인을 확인하지 못했습니다." (버튼 없음)

---

## POST /records

파일 업로드. `multipart/form-data`.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | R1 "+ 파일 올리기", 카테고리별 "올리기 +" |
| 응답 | 201, `parseStatus=PARSING` |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `file` | binary | ✓ | |
| `clubId` | string | ✓ | |
| `category` | enum | | 생략 시 AI 분류 후 `ETC` 기본 |
| `eventId` | string | | 특정 행사 연결 |

```
POST /api/v1/records
Content-Type: multipart/form-data

file: (binary) 2025 하반기 장부.xlsx
clubId: clb_3a71c0
category: LEDGER
```

```jsonc
// 응답 (201) — 파싱은 비동기로 진행
{
  "data": {
    "id": "rec_14",
    "fileName": "2025 하반기 장부.xlsx",
    "fileType": "XLSX",
    "category": "LEDGER",
    "size": 48211,
    "parseStatus": "PARSING",
    "createdAt": "2026-03-02T12:00:00Z"
  },
  "meta": null
}
```

> **미정**: 업로드 시 카테고리를 사용자가 고를지, AI가 분류하고 확인만 받을지. 후자면 응답에 `suggestedCategory`가 필요합니다.

---

## PATCH /records/{recordId}

카테고리 변경. R1 "분류 다시 하기".

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `category` | enum | |

```jsonc
// 요청
{ "category": "LEDGER" }
```

```jsonc
// 응답
{
  "data": { "id": "rec_09", "category": "LEDGER", "parseStatus": "PARSING" },
  "meta": null
}
```

> 카테고리를 바꾸면 파서가 달라지므로 `parseStatus`가 `PARSING`으로 되돌아갑니다.

---

## DELETE /records/{recordId}

파일 삭제. R1 "이 파일 삭제".

| 항목 | 내용 |
| --- | --- |
| 응답 | 204 (본문 없음) |

```
DELETE /api/v1/records/rec_11
```

---

## POST /records/{recordId}/column-mapping

장부 파일의 열 이름이 표준과 달라 파싱이 멈췄을 때, 사용자가 직접 열을 연결합니다.
`parseError` 처리에서 `COLUMN_MISMATCH`일 때 "열 직접 맞추기"에 대응하는 엔드포인트입니다.

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | R1 "열 직접 맞추기" |
| 비고 | 매핑 저장 후 재파싱. `parseStatus`가 `PARSING`으로 돌아감 |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `mapping` | object | ✓ | `{ 표준 열 이름: 파일의 실제 열 이름 }` |

```jsonc
// 요청
{
  "mapping": {
    "날짜": "일자",
    "적요": "내용",
    "입금": "금액",
    "출금": "금액"
  }
}
```

```jsonc
// 응답
{
  "data": { "id": "rec_09", "parseStatus": "PARSING" },
  "meta": null
}
```

> 위 예시처럼 입금·출금이 한 열(`금액`)에 섞여 있고 `구분` 열로 나뉘는 경우가 실제로 흔합니다.
> **이 형태를 매핑만으로 풀 수 있는지 BE 확인이 필요합니다.** 부호 판별 규칙이 별도로 필요할 수 있습니다.

---

## GET /records/template

장부 CSV 양식 다운로드. R1 "양식 받아서 다시 만들기".

| 항목 | 내용 |
| --- | --- |
| 응답 | `text/csv` 파일 스트림 |

**요청 쿼리**

| 파라미터 | 타입 | 설명 |
| --- | --- | --- |
| `category` | enum | 현재는 `LEDGER`만 양식 제공 |

```
GET /api/v1/records/template?category=LEDGER
```

---

## POST /records/chat

동아리 기록에 대해 질문합니다. **세션을 저장하지 않으므로 대화 이력을 매 요청에 실어 보냅니다.**

| 항목 | 내용 |
| --- | --- |
| 호출 화면 | R1 하단 챗봇 바, R1-b 패널 |
| 비고 | `Conversation`/`Message`에 저장하지 않음. `AgentLog(feature=RETRIEVAL)`에만 기록 |

**요청**

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `clubId` | string | ✓ | |
| `messages` | array | ✓ | 이전 대화 전체 + 이번 질문 |

```jsonc
// 요청 — 세션이 없으므로 이전 대화를 매번 함께 보냄
{
  "clubId": "clb_3a71c0",
  "messages": [
    { "role": "USER",      "content": "작년 봄 MT 때 1인당 얼마 걷었어?" },
    { "role": "ASSISTANT", "content": "1인당 40,000원이었습니다. 32명에게 걷어 총 1,280,000원이고..." },
    { "role": "USER",      "content": "그때 예비비 모자랐다고 했었나?" }
  ]
}
```

**응답**

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `content` | string | 답변 본문 |
| `sources` | array | "근거로 쓴 기록". `location`은 v1에서 객체로 변경 |
| `notFound` | string \| null | "기록에 없는 것" |
| `suggestions` | string[] | "이어서 물어볼 만한 것" |

**`sources[].location`: 문자열 → 객체 (v1 변경)**

내부 구조(`sheet`·`row`·`page`)는 청킹 방식이 정해져야 나옵니다. 지금은 `label` 하나만 두고, 타입을 객체로 열어둬서 나중에 필드가 늘어도 FE가 깨지지 않게 합니다.

```jsonc
{
  "data": {
    "content": "네. 예비비 130,000원을 잡았는데 실제로는 172,000원을 썼고, 초과분 42,000원은 총무가 먼저 내고 나중에 정산했습니다.",
    "sources": [
      { "recordId": "rec_03", "fileName": "2025 하반기 장부.xlsx", "location": { "label": "회비 수납 시트" } },
      { "recordId": "rec_05", "fileName": "2025 봄 MT 결과보고.hwp", "location": { "label": "예산 항목" } }
    ],
    "notFound": "무엇에 초과 지출했는지는 장부에 항목이 비어 있어 확인할 수 없습니다.",
    "suggestions": [
      "올해는 예비비를 얼마로 잡는 게 좋을까?",
      "작년 MT 참가 취소는 몇 건이었어?"
    ]
  },
  "meta": null
}
```

> **FE 작업**: `location`을 바로 쓰던 곳을 `location.label`로 변경.

---

---

# 5. BE 스키마 관련

FE 명세를 쓰면서 현재 스키마로는 그릴 수 없는 화면이 나왔습니다.
🔸로 표시한 필드가 그것이며, **전부 FE가 임시로 넣은 것이고 BE와 합의된 바 없습니다.**

무엇이 왜 필요한지는 별도 문서로 정리했습니다 → **`운영해_BE_스키마_검토요청.md`**, BE 답변은 **`운영해_BE_스키마_검토안.md`**

이 명세는 그 요청이 받아들여진다는 가정 없이, 🔸 필드가 `null`로 내려오는 상태에서도
화면이 빈 값으로 그려지도록 작성했습니다.

v1에서는 BE 검토안 §4의 응답 형식 변경 6건과 인원 필드명 통일(`headcount`) 1건만 반영했고, 스키마가 실제로 확정한 나머지 필드(`steps.phase`, `plan_warnings`/`plan_excluded_steps`, `events.end_date`, `event_type`/`location`, `budget_total`/`fee_per_person`/`expected_headcount`, `actions.amount`/`deny_reason`/`payload` 등)를 🔸에서 확정 표기로 바꾸는 작업은 별도로 진행합니다.
