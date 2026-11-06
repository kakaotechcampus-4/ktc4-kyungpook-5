# 행사 운영 상황 확인 API

진행 중(`ON_GOING`) 행사에서 회장·임원이 상황을 입력하고 확인 질문과 답변 기반 제안을 기록한다. 행사 소속 권한을 매 요청 확인한다. 발송·예약·이체·행사 계획 변경은 수행하지 않는다. 기존 opaque Bearer 인증, camelCase, Envelope 및 오류 형식을 사용한다.

- `POST /api/v1/events/{eventId}/operation-cases`: `{clientRequestId, situation}`. 상황은 공백 제외 1~4000자. 상황을 우선 저장하고 AI가 질문이 필요하다고 판단한 경우에만 행사에 직접 속하는 `CONFIRMATION` Action을 생성한다(`stepId: null`). 충분하면 질문 없이 결과를 저장한다. 같은 행사와 clientRequestId의 동일 상황은 기존 사례를 반환하고 다른 상황은 409다. 응답 `data`는 아래 사례 객체다.
- `GET /api/v1/events/{eventId}/operation-cases?page=1&size=20`: 사례 최신순 목록과 페이지 meta. `GET /api/v1/events/{eventId}/operation-cases/{caseId}`는 단건 복원.
- `POST /api/v1/events/{eventId}/operation-cases/{caseId}/question`: 질문 생성 실패 후 명시 재시도. 성공 사례는 기존 결과를 반환한다.
- `POST /api/v1/actions/{actionId}/resolve`: 기존 `{expectedVersion, choice, manualValue?}` 계약으로 먼저 답을 저장한다. 선택 답 또는 `MANUAL` 직접 입력(200자 이내)을 원답으로 보존한다.
- `POST /api/v1/events/{eventId}/operation-cases/{caseId}/result`: 저장된 답을 바탕으로 제안을 생성한다. 답이 없으면 409, 이미 완료된 결과는 그대로 반환한다. 실패 후 동일 경로로 재시도할 수 있으며 다시 질문하지 않는다.

사례 객체: `{id,eventId,clientRequestId,situation,questionStatus,action,resultStatus,result,error,createdAt,modifiedAt}`. `action`은 기존 ActionOut이며 선택한 `resolvedChoice`/`manualValue`와 options로 원답 및 선택 label을 복원한다. 질문 상태는 `PENDING`, `PROCESSING`, `NEEDS_ANSWER`, `NO_QUESTION`, `FAILED`, 결과 상태는 `NOT_REQUESTED`, `PROCESSING`, `READY`, `FAILED`. `result`는 `{summary,suggestions}` 또는 null이고 `error`는 안전한 `{code,message}` 또는 null이다. PENDING/PROCESSING은 질문·답변 생성 성공을 뜻하지 않는다. AI 오류는 저장된 사례와 FAILED로 표시하며 사용자의 상황 또는 이미 저장된 답은 삭제하지 않는다.

동일 생성 요청은 처리 중에도 기존 사례를 반환한다. 질문·결과 실행 재요청이 처리 중이면 409 `OPERATION_IN_PROGRESS`. 저장 직후 중단되어 `PENDING`이면 질문 재시도로 복구한다. 일정 시간 이후 재시도는 이전 시도를 무효화하며 늦게 도착한 이전 결과를 저장하지 않는다. AI 호출 전후 소속과 행사 상태를 재확인한다. 권한 없음 403, 다른 행사에 속한 사례/없는 사례 404, 진행 중이 아닌 행사나 답변 전 결과 요청은 409, 입력 형식 오류는 422. 모델 출력은 검증하며 오류 세부나 비밀은 클라이언트에 전달하지 않는다. 입력과 결과는 사용자 데이터이며 외부 지시로 취급하지 않는다.

## 공지·발송 Action 본문 초안 (#334)

운영 중(`ON_GOING`) 행사에서 어떤 단계가 **현재 단계**(완료되지 않은 첫 단계)가 되면, 그 단계의 공지(`NOTICE`)·발송(`EXTERNAL_SEND`) Action에 토리가 본문 초안을 쓴다. 토리는 글만 쓰고, 운영진이 고쳐서 승인한 뒤 앱 밖에서 직접 올린다. 코드는 `app/services/action_draft_service.py`, 판정은 `event_rules`(`can_request_draft`, `shown_content_status`)에 있다.

예: 단계 1 "담당 인원 배치"를 완료하면

```
POST /steps/{id}/complete
  → 단계 완료, 커밋
  → request_current_step_drafts(eventId)
       현재 단계 = "모집 공지"
       Action "모집 공지 올리기"(NOTICE, PENDING, 본문 없음, NONE) → DRAFTING, draft_attempt_id=A1, 커밋
       asyncio 작업으로 _run_draft(actionId, A1)
  → 응답은 AI를 기다리지 않고 바로 돌아옴

뒤에서 _run_draft (새 DB 세션)
  → Event·Step·Action·Club을 읽어 ai.ActionDraftRequest를 만든다
       단계 starts_at·deadline은 한국 시간 날짜로 바꾼다 (2026-04-30T15:00:00Z → 2026-05-01). 총예산은 넣지 않는다
  → 잠금 없이 ai.draft_action_content(request)
  → 행사·Action을 잠그고 저장 조건을 확인한 뒤 저장
```

- **신호를 보내는 곳**: `action_service`의 `start_event`(첫 단계), `mark_done`·`resolve`(단계 자동 완료), `complete_step`(직접 완료). 모두 커밋한 뒤에 부르며, 실패해도 호출한 쪽의 응답은 성공한다.
- **대상**: 현재 단계의 `NOTICE`·`EXTERNAL_SEND` 중 `status=PENDING`, 본문 없음, `contentStatus=NONE`. 현재 단계가 되기 전에 미리 승인한 Action은 `PENDING`이 아니라서 쓰지 않는다. 계획 중(P1·P2) 행사에는 동작하지 않는다.
- **저장 조건** (모두 만족해야 저장, 아니면 결과를 버림): 같은 `draft_attempt_id`, `status=PENDING`, 본문이 비어 있거나 `contentSource=AI`, 행사가 아직 `ON_GOING`. 저장하면 `READY`·`AI`·`contentUnknowns`(본문의 `[ ]`)를 남기고 `version`을 1 올린다. 그래서 초안 도착 전 화면을 보고 승인하면 `VERSION_CONFLICT`가 난다. 버린 경우 작성 중 표시만 `NONE`으로 걷어 낸다.
- **실패**: `FAILED`와 `draft_error_code`. `AIInvalidResponseError` → `AI_INVALID_RESPONSE`, 그 밖의 `AIRetryableError` → `AI_UNAVAILABLE`, 나머지 예외 → `INTERNAL_ERROR`(서버 로그). 실패해도 단계 진행·승인은 막지 않는다.
- **멈춘 작성**: `DRAFTING`인데 시작한 지 3분이 지났으면(서버 재시작 등) 응답에서만 `FAILED`로 보이고 다시 받을 수 있다. DB 값은 그대로다.

### API

| API | 내용 |
| --- | --- |
| Action 응답(`ActionOut`) | `contentStatus`(`NONE`/`DRAFTING`/`READY`/`FAILED`), `contentSource`(`AI`/`USER`/null), `contentUnknowns`(`string[]`), `canRequestDraft`(아래 `POST /draft` 허용 조건과 같은 값) |
| `POST /api/v1/actions/{actionId}/draft` | 「초안 다시 받기」. `{expectedVersion}`. 성공하면 `DRAFTING`, 이전 토리 본문을 비우고 `version` +1, `data: ActionOut`. 허용: 운영 중, `PENDING`, 대상 종류, `contentSource`가 `USER` 아님, 초안을 요청한 적 있음(`NONE` 아님), 작성 중이 아님(3분 넘게 멈춘 작성은 허용). 아니면 409 `DRAFT_NOT_ALLOWED`(운영 중이 아닌 행사 포함). 본 뒤 바뀌었으면 409 `VERSION_CONFLICT`, 없으면 404 `ACTION_NOT_FOUND` |
| `PATCH /api/v1/actions/{actionId}` | `content` 추가. 바뀌면 `contentSource=USER`, `contentStatus=READY`, `contentUnknowns=[]`, `version` +1. 승인된 Action이면 `PENDING`으로 돌아간다(기존 동작). 빈 문자열·공백만·null이면 422 `VALIDATION_FAILED`. 응답은 기존 `PlannedStepOut` 그대로 |

운영진이 고친 본문(`USER`)은 토리가 덮어쓰지 않는다. 작성 중에 고쳐도 사람의 글이 남고 늦게 온 초안은 버린다.
