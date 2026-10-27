# 운영해 FE 연동 기준서

> 2026-10-27. 작성: FE(박수겸).
> **기준:** BE 현재 구현(`be/app/routers`·`schemas`·`models`) + AI `be/app/ai/contracts.py` + 열린 이슈.
> **FE 연동은 이 문서를 기준으로 합니다.** `docs/week6/fe/운영해_FE_API_명세_v1.md`는 2026-09-18 기준이라 기준에서 내립니다 — 다만 아직 구현 안 된 쓰기 경로의 요청 명세가 거기에만 있어 **참고 자료로는 남깁니다**.

---

## 0. 계약이 어디에 있나

가장 먼저 합의할 것은 "누가 무엇의 기준인가"입니다. 지금 계약 문서가 여러 곳에 흩어져 있어 이것부터 적습니다.

```
FE  ──HTTP, camelCase──→  BE                  ──Python, snake_case──→  AI
                          app/schemas/*.py                             app/ai/contracts.py
                                              ←──────────────────────  app/ai/ports.py
                                                 (AI가 BE에 요구하는 것)
```

**`contracts.py`는 HTTP 계약이 아닙니다.** BE와 AI가 **같은 프로세스 안에서 함수로** 주고받는 Python 타입입니다. 파일 머리말에 그렇게 적혀 있습니다.

> "BE와 AI는 같은 프로세스 안에서 함수로 호출되므로 필드명은 snake_case를 사용한다. 외부 API의 camelCase 변환은 BE의 `app/schemas/`에서 처리한다."

그래서 **"FE가 `contracts.py`를 따른다"는 말의 정확한 뜻은 — BE가 `PlanningView`를 camelCase 변환만 해서 통과시켜 달라**는 것입니다. 중간에서 BE가 다시 빚으면 Figma·AI·BE 세 곳으로 갈라집니다.

`ports.py`는 **반대 방향**입니다. AI가 BE에게 해달라고 요구하는 것이고, 지금은 `RecordSearchPort.search_chunks()` 하나입니다. **회의 판단이 아직 더미인 이유가 이것**입니다(§3).

**`contracts.py`에 있으면 합의된 것, 없으면 아직입니다.** 회의 판단 타입은 `features/meeting/schemas.py`에 따로 있고, 그 파일에 "BE와 합의하기 전이라 `contracts.py`에 두지 않고, 합의하면 옮긴다"고 적혀 있습니다.

### 영역별 기준 문서

| 영역 | 기준 | 상태 |
| --- | --- | --- |
| 행사 목록·상세·단계·행동 (읽기) | `be/app/schemas/events.py` | 확정·구현됨 |
| 행사 승인·거절·단계 수정 (쓰기) | 명세 v1 §3 (요청 명세) | **미구현** · #41 |
| P1·P2 계획 | **`be/app/ai/contracts.py`** | AI 확정 · HTTP 없음 |
| 계획 요약 패널 | **아무도 정의 안 함** | #177에서 논의 중 (§5.3) |
| 동아리 기록 | `be/app/schemas/records.py` + 명세 v1 §4 | 일부 구현 · #42 |
| 회의 | `be/app/ai/features/meeting/schemas.py` | 초안 · #113 |
| 인증·동아리 | `be/app/schemas/auth.py`·`clubs.py` | 구현됨 |
| 정산 | `be/app/schemas/accounting.py` | 구현됨 · 화면 없음 |

---

## 1. 지금 바로 붙일 수 있는 것

FE는 현재 **서버를 한 번도 부르지 않습니다.** `features/events/hooks.ts`의 모든 `queryFn`이 `?demo`면 mock, 아니면 빈 값입니다. 아래 셋은 **오늘 교체 가능합니다.**

### 1.1 행사 목록 — `GET /api/v1/events`

```
?clubId= &status=PLANNING|ON_GOING|COMPLETE &page=1&size=20
```

`EventOut`과 FE `EventSummary`가 **필드 이름까지 1:1**입니다.

```
id title status startDate endDate dday location headcount
currentStepName stepProgress[{stepOrder,state}] pendingApprovalCount
payment(=null) budget(=null)
```

> FE `events/types.ts`에 "`location`·`headcount`는 응답에 아직 없다"는 TODO가 있는데 **틀렸습니다.** 둘 다 내려옵니다. **이슈 #92(「GET /events 응답에 location·expectedHeadcount 추가」)는 이미 완료 상태라 닫아도 됩니다.**

### 1.2 단계 목록 — `GET /api/v1/events/{eventId}/steps`

`StepOut`에 `doneActions`·`remainingActions`·`completedCount`·`totalActionCount`·`completedAt`이 다 들어 있어 **L2 진행 상황과 Step 모달이 한 번에** 삽니다.

### 1.3 행동 목록 — `GET /api/v1/events/{eventId}/actions`

| 화면 | 쿼리 |
| --- | --- |
| M1 승인 대기 | `status=PENDING&excludeType=CONFIRMATION` |
| L2 확인 요청 | `status=PENDING&type=CONFIRMATION` |
| L2 처리된 승인 | `status=APPROVED,DONE,DENIED&size=3` |

`meta.totalCount`가 와서 「12건 중 3건」 표시가 됩니다. `options`/`allowManual`은 `payload`에서 펼쳐 내려옵니다.

### ⚠️ 붙이기 전에 알아야 할 것 둘

1. **데이터가 fixture입니다.** `event_service.py` 머리말: *"현재는 mock 단계다(#30). DB가 없어 고정 fixture를 반환한다."* 행사는 `evt_9f2c8a` 하나뿐입니다. **연결은 진짜, 데이터는 하나**입니다. 시연에는 당분간 `?demo`가 낫습니다.
2. **`/events` 3개에만 인증이 없습니다.** 다른 라우터는 전부 `Depends`가 걸려 있는데 여기만 없습니다. 지금은 토큰 없이 붙지만, 나중에 인증이 붙는 순간 401이 쏟아집니다. **BE에 "인증을 붙일 계획인지" 확인이 필요합니다.**

---

## 2. P1·P2 계획 — `contracts.py` 기준

### 2.1 AI는 준비됐습니다

`chat_planning()` / `generate_planning_preview()`가 실제 모델로 동작하는 것까지 확인된 상태입니다(`p1-handoff.md`, 2026-10-25). 화면에 필요한 값이 전부 타입으로 있습니다.

| 화면 | `view`의 값 |
| --- | --- |
| 토리 말풍선 | `reply` |
| 조건 카드 값 | `draft.conditions` — **`null`=미정, `0`=무료** |
| 확정 / 잠정 | `draft.condition_meta[field].status` = `specified` \| `tentative` |
| 잠정 근거 인용 | `draft.condition_meta[field].evidence.quote` |
| 「나중에」 칩 | `draft.deferred_topics` |
| 「다음」 버튼 활성 | `generation_readiness.can_generate` + `reasons[]` |
| 찾아본 기록 | `record_lookup.status` = `available` \| `not_found` \| `failed` \| `rejected` |
| 생성 결과 | `generation_result.status` = `generated` \| `needs_clarification` \| `failed` |

**#179에서 합의한 것이 이미 반영돼 있습니다** — 4상태 조건 카드가 표현 가능하고, 「6개 중 4개」 게이팅은 `reasons`가 `event_type_missing`·`condition_change_pending` 둘뿐이라 사라졌고, 「자료 없음」과 「검색 실패」도 나뉘어 있습니다. **Figma v13 P1은 이 계약대로 그렸으므로 어긋나는 데가 없습니다.**

주의할 규칙 둘:

- **답변 문장의 숫자로 조건 카드를 바꾸지 않습니다.** 상담에서 "3만 원이면…"이라 해도 구조화된 값이 25,000원이면 그대로입니다.
- **`changed_fields`로 부분 갱신하지 않고 `draft` 전체로 갈아끼웁니다.** 값이 같아도 잠정/보류가 바뀔 수 있습니다.

### 2.2 없는 것

| 필요한 것 | 현재 |
| --- | --- |
| HTTP 경로 | **없음** |
| `next_state` 보관 컬럼 | **없음** — `Event` 모델에 계획 상태 컬럼이 없음 |
| `base_revision`(낙관적 잠금) 컬럼 | **없음** |
| BE가 `chat_planning()`을 부르는 코드 | **0건** (`app/ai` 바깥에 호출부 없음) |

**FE가 할 수 있는 일이 없습니다.** 다만 BE가 경로를 열 때 §0의 전제(`view`를 camelCase 변환만)를 **지금 못 박아 두는 것**이 FE가 할 수 있는 유일한 일입니다.

### 2.3 `next_state`가 왜 필요한가 (BE 설득용)

명세 v1 시절 모델은 "서버가 `Message` 테이블을 다시 읽어 조건을 추출한다"였습니다. 그걸로는 이게 안 풀립니다.

```
사용자: "참가비 3만 원이면 어때? 아직 바꾸지는 마"
AI:     상담만 → 참가비는 25,000원 유지
사용자: "일단 그렇게 잡자"
        ↑ "그렇게"가 3만 원인 줄 알려면 앞선 상담과 Tool 이력이 남아 있어야 함
```

Tool 호출 이력은 `Message.content` 텍스트에 안 남습니다. **필드를 더해서 되는 문제가 아니라 보관 모델이 필요합니다.** 이력 한도는 Tool 메시지 포함 60개(`MAX_PLANNING_HISTORY`)입니다.

---

## 3. 회의 M2

**경로는 끊긴 데 없이 다 있습니다.**

```
POST /clubs/{clubId}/meetings          회의 생성 (recordingConsentConfirmed 필수)
POST /meetings/{id}/audio-chunks       음성 청크 (multipart, seq/startMs/endMs)
GET  /meetings/{id}/transcripts        전사 목록 (?afterSeq= 커서)
WS   /meetings/{id}/stream?token=      판단 결과 수신
POST /meetings/{id}/finish             종료
```

**속은 전부 더미입니다.**

| 자리 | 현재 |
| --- | --- |
| STT | `meeting_stt_stub` → `"(더미 전사) 3번 음성 청크 1000~4000ms 구간입니다."` |
| 판단 | `meeting_judge_stub` — 물음표면 RAG, "써줘/만들어"면 LLM |
| 기록 검색 | `context_tools_stub` |
| 색인 | 안 돎 (`record_service.py`: "청크 저장소가 아직 없어 하지 않는다") |

**AI 쪽에는 진짜 `judge_utterance()`가 공개돼 있습니다.** `JudgeUtteranceResult`에 `kind`(`NO_LOOKUP`/`ANSWER`/`NOT_FOUND`)·`question`·`answer`·`sources`가 있고, #110이 요구한 「기록에 없음」과 「처리 실패」 구분이 검증기로 강제돼 있습니다. **BE가 `RecordSearchPort`를 구현하면 바로 붙습니다 — 그게 #141입니다.**

**FE가 지금 할 수 있는 것:** 전사 표시(v13 M2의 발화 박스)와 `afterSeq` 커서 폴링, WS 수신은 **지금 붙여서 검증 가능합니다.** 문장이 더미일 뿐 흐름은 진짜입니다.

**단, `speakerLabel`은 항상 `null`입니다.** 발화자 구분은 #118에서 범위 밖으로 뺐습니다. Figma에서 발화자를 색으로 나눴다면 지워야 합니다.

---

## 4. 화면별 판정

| Figma v13 묶음 | 상태 | 담당 이슈 |
| --- | --- | --- |
| M1 메인 (행사·승인 대기) | 🟢 오늘 연결 | #41 |
| M1 토리 판단 카드 | 🟡 `GET /clubs/{id}/context-decisions` 매핑 (§5.4) | #137 |
| L1 행사 목록 | 🟢 오늘 연결 | #41 |
| L2 행사 상세 헤더 | 🟡 단건 경로 없음. 목록에서 걸러 우회 가능 | #41 · #80 |
| L2 진행 상황 · 모달 Step | 🟢 오늘 연결 | #41 |
| 모달 · 결정 검토 (승인/거절) | 🔴 **쓰기 경로 없음** | #41 (미체크) |
| 모달 · Step 세부 수정 | 🔴 쓰기 경로 없음 | #41 (미체크) · #106 |
| P1 큰 틀 잡기 · P1-c 생성 중 | 🟠 AI 준비됨 · HTTP·DB 없음 | #179 |
| P2 흐름 만들기 | 🟠 위와 같음 | #177 |
| P2-b 계획 수정 (AI 검토) | 🔴 AI 쪽에도 없음 | #177 |
| L2-d 행사 취소 정리 | 🔴 enum만 있음 | #73 |
| M2 회의 | 🟡 경로 있음 · 속은 더미 | #119 · #141 |
| S0 로그인 | 🟡 경로 완비 · FE에 `auth/api.ts` 없음 | — |
| S1 회원가입 | 🟡 가입은 되나 **동아리 검색 API 없음** | **이슈 없음** |
| S2 · 내 정보 | 🟡 `GET /me`에 이름·가입일 없음 | — |
| S2 · 동아리원 | 🔴 **목록 API 없음** | **이슈 없음** |
| S2 · 동아리 자료 | 🟠 업로드·단건만. **목록 없음** | #42 |
| 모달 · 동아리원 추가 | 🟡 초대는 됨. 계정 없는 명단 추가는 미확인 | — |
| 상태 화면 · 토스트 | 🟢 서버 무관 | — |
| 0 · 기준 / 참고 · 13단계 | — | 참고용 |

---

## 5. 결정된 것과 남은 것

### 5.1 확정 (이번에 정함)

| 항목 | 결정 |
| --- | --- |
| P1·P2 계약 | **`contracts.py`를 따른다.** 명세 v1 §1은 폐기 |
| `title` | **BE가 채운다.** `Event.title`은 `nullable=False`이고 AI는 초안 단계에서만 `None`을 허용. 층이 다른 것이지 모순이 아님 |
| `RecordCategory` | **BE를 따른다** — `LEDGER`/`ETC`/`RULES`/`EVENT_HISTORY`/`RECEIPT` |
| `RecordParseStatus` | **BE를 따른다** — 6개 (`QUEUED` 포함) |
| 예산·수납(`payment`/`budget`) | **BE `accounting` 기준으로 재정의.** 기존 `transactions`/`participants` 전제는 폐기 |

> **#179에 정정 코멘트가 필요합니다.** `title = null`에 대해 FE가 "빈칸 선호"라고 답했는데, 위 결론과 반대입니다.

### 5.2 `warnings` — AI에 요청할 것

`contracts.py`의 `EventPlanPreview.warnings`가 `tuple[str, ...]`입니다. **규칙이 센 사실인지 AI 의견인지 구분이 없습니다.**

#177에서 ④ 규칙 경고(사실, BE) / ⑤ AI 검토(의견, 토리)로 나누기로 했는데, **지금 타입으로는 화면에서 그 구분을 지킬 수 없습니다.** `source` 구분을 넣어 달라고 요청해야 합니다.

같은 맥락으로 `ExcludedPlanStep.code`는 `StepCode`만 옵니다 — FE가 단계 이름을 띄우려면 `catalogue.ts`로 매핑하거나 AI가 `name`도 줘야 합니다. 어느 쪽인지 정해야 합니다.

### 5.3 계획 요약 — **아무도 정의하지 않았습니다**

| | 정의했나 |
| --- | --- |
| AI | **안 한다고 명시** — `PlanDraft` 주석: *"단계 수·담당별 개수 같은 요약값은 세면 나오므로 담지 않는다. BE가 계산한다."* |
| BE | 아직 |
| FE | #177 코멘트가 **유일한 글** |

그래서 #177에서 BE가 물어본 것입니다. FE가 올린 정의(기간 = 준비 기간 / 수금 = 수금 Action 개수, **공통 금액 전제** / 공지 = 공지 Action 개수)대로 **BE가 계산해 내려주면 됩니다.**

**단 구조화된 값으로 받습니다.** 지금 FE `PlanSummary`는 `collect: "1회 · 1인 45,000원"`, `period: "3/2 → 3/25"`처럼 **문장을 통째로** 받게 돼 있습니다. 서버가 조립한 문장을 화면에 그대로 뿌리지 않기로 한 프로젝트 규칙에 어긋나므로, `{times, feePerPerson}` / `{periodStart, periodEnd}`로 받아 FE가 조립합니다.

### 5.4 그 밖에 BE에 요청할 작은 것들

| 요청 | 크기 |
| --- | --- |
| `ActionOut`에 `content` 싣기 — **DB 컬럼(`actions.content`)은 있는데 응답 스키마에 없어 FE까지 안 옴.** 승인 전 토리 초안 문구 표시에 필요 | 한 줄 |
| `ContextDecisionOut.citations`가 `list[dict]`로 열려 있음 — 모양 고정 | 작음 |
| `/events` 3개 인증 계획 확인 | 질문 |
| 대화 60개 한도의 남은 여유를 응답에 싣기 (#179에서 이미 요청) | — |

---

## 6. 이슈 정리

조사하면서 **이슈 쪽이 실제와 어긋난 것**이 보였습니다. 이것부터 맞춰야 혼선이 줄어듭니다.

| 이슈 | 문제 | 조치 |
| --- | --- | --- |
| **#92** | "GET /events에 location·expectedHeadcount 추가" — **이미 구현됨** | **닫기** |
| **#41** | BE 체크리스트의 P1/P2 항목이 전부 명세 v1 경로(`/conversations/{id}/messages`, `plan:generate`, `GET /plan` …). **`contracts.py`로 대체됐음** | P1/P2 절 교체 |
| **#41** | FE 항목이 `features/planning/hooks.ts`를 가리키는데 **그 파일이 없음** (planning에는 `mock.ts`·`types.ts`뿐) | 문구 수정 |
| **#42** | `features/records/api.ts`를 가리키는데 **`features/records`가 없음** (`mypage/components/RecordsTab.tsx`) | 문구 수정 |
| — | **동아리원 목록 API** — 화면은 있는데 이슈가 없음 | **신설** |
| — | **동아리 검색 API** — `ClubSearchField.tsx`가 있는데 이슈가 없음 | **신설** |

**승인·거절은 새 이슈가 필요 없습니다.** #41 체크리스트에 이미 `POST /actions/{id}/approve` / `/deny` / `/resolve`와 `POST /steps/{id}/complete`가 미체크로 들어 있습니다. **우선순위만 올리면 됩니다** — 이게 없어서 지금 앱이 읽기 전용입니다.

---

## 7. FE가 서버 없이 지금 고칠 것

| # | 할 일 | 이유 |
| --- | --- | --- |
| 1 | **`npm run gen:api-types`** | `schema.d.ts`에 경로가 **3개뿐**. BE는 38개. 서버를 안 띄우려면 `be/`에서 `uv run python -c "import json,pathlib; from app.main import app; pathlib.Path('openapi.json').write_text(json.dumps(app.openapi()),encoding='utf-8')"` 로 덤프한 뒤 그 파일을 넘긴다 |
| 2 | enum 맞추기 | `RecordCategory` 5값 · `ParseStatus` 6값 · `fileType` 5값(`HWP`·`IMAGE` 누락) · **`EventStatus` 5값**(`CANCELLING`·`CANCELLED` 누락). **스키마를 새로 뽑아도 타입 오류로는 안 드러난다** — FE 도메인 타입이 손으로 쓴 것이라 생성 타입과 이어져 있지 않다. 눈으로 대조해야 한다 |
| 3 | `catalogue.ts` StepCode 5개 수정 | `ASSIGN_STAFF`→`ASSIGN_ROLES`, `SCOUT_VENUE`→`RESEARCH_VENUE`, `SURVEY_DEMAND`→`DEMAND_SURVEY`, `CONFIRM_HEADCOUNT`→`CONFIRM_DETAILS`, `PRE_NOTICE`→`PRE_EVENT_NOTICE`. **AI는 `StepCode` 중에서만 고르므로 초안이 오는 날 전부 매칭 실패** |
| 4 | `PlanGeneratingScreen` 수정 | `ProgressBar`로 **가짜 진행률**을 보임. #179에 "가짜 진행은 그리지 않겠다"고 올리고 v13을 그렇게 그렸는데 코드가 반대 |
| 5 | `PlanFacts.tsx`의 `REQUIRED = 4` 제거 | #177에서 폐기 합의. `PlanFacts` 타입도 `{value, decided:boolean}`으로는 **4상태를 못 담음** |
| 6 | `PlanSummary` 구조화 | §5.3 |
| 7 | 낡은 주석 정리 | `events/types.ts`(location·headcount), `dashboard/types.ts`(판단 API 없음), `fe/README.md`(없는 폴더·파일 나열) |

---

## 8. 순서

```
지금      ① FE 자체 정리 7건 (서버 무관, 반나절)
          ② 이슈 정리 — #92 닫기, #41/#42 문구 수정, 신규 2건
          ③ #179에 title 정정 코멘트

다음      ④ 🟢 3개 연결 (M1·L1·L2 읽기) — hooks.ts queryFn 교체
          ⑤ #41 승인·거절 우선순위 올리기 요청
          ⑥ 회의 전사 흐름 붙여 보기 (더미여도 커서·WS 검증됨)

기다림    ⑦ P1 HTTP·DB (BE)        ⑧ AI 검토 (AI)
          ⑨ 자료·동아리원 목록 (BE)  ⑩ 취소 정리 (#73)
```

---

## 부록. 확인한 곳

| 주장 | 파일 |
| --- | --- |
| FE가 서버를 안 부름 | `fe/src/features/events/hooks.ts` |
| `/events`가 fixture | `be/app/services/event_service.py:1-8`, `:172` |
| `/events`에 인증 없음 | `be/app/routers/events.py` (`Depends` 0건) |
| P1 호출부 없음 | `grep -rn "chat_planning" be --include=*.py` → `app/ai` 바깥 0건 |
| P1 계약 | `be/app/ai/contracts.py` (`PlanningView`·`PlanningDraft`·`ConditionMeta`) |
| 요약은 BE 몫 | `be/app/ai/contracts.py` `PlanDraft` docstring |
| `warnings`가 문자열 튜플 | 같은 파일 `EventPlanPreview.warnings` |
| 계층·snake_case 규칙 | 같은 파일 머리말 |
| AI가 BE에 요구하는 것 | `be/app/ai/ports.py` (`RecordSearchPort`) |
| 회의 더미 | `be/app/services/meeting_stt_stub.py`·`meeting_judge_stub.py` |
| 진짜 회의 판단 | `be/app/ai/features/meeting/schemas.py` (`JudgeUtteranceResult`) |
| `Action.content` 컬럼 존재 | `be/app/models/events.py` Action 절 |
| `ActionOut`에 `content` 없음 | `be/app/schemas/events.py` |
| 승인·거절이 #41에 있음 | `gh issue view 41` 체크리스트 |
