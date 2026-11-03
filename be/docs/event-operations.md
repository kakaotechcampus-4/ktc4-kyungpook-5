# 행사 운영 상황 확인 API

진행 중(`ON_GOING`) 행사에서 회장·임원이 상황을 입력하고 확인 질문과 답변 기반 제안을 기록한다. 행사 소속 권한을 매 요청 확인한다. 발송·예약·이체·행사 계획 변경은 수행하지 않는다. 기존 opaque Bearer 인증, camelCase, Envelope 및 오류 형식을 사용한다.

- `POST /api/v1/events/{eventId}/operation-cases`: `{clientRequestId, situation}`. 상황은 공백 제외 1~4000자. 상황을 우선 저장하고 AI가 질문이 필요하다고 판단한 경우에만 행사에 직접 속하는 `CONFIRMATION` Action을 생성한다(`stepId: null`). 충분하면 질문 없이 결과를 저장한다. 같은 행사와 clientRequestId의 동일 상황은 기존 사례를 반환하고 다른 상황은 409다. 응답 `data`는 아래 사례 객체다.
- `GET /api/v1/events/{eventId}/operation-cases?page=1&size=20`: 사례 최신순 목록과 페이지 meta. `GET /api/v1/events/{eventId}/operation-cases/{caseId}`는 단건 복원.
- `POST /api/v1/events/{eventId}/operation-cases/{caseId}/question`: 질문 생성 실패 후 명시 재시도. 성공 사례는 기존 결과를 반환한다.
- `POST /api/v1/actions/{actionId}/resolve`: 기존 `{expectedVersion, choice, manualValue?}` 계약으로 먼저 답을 저장한다. 선택 답 또는 `MANUAL` 직접 입력(200자 이내)을 원답으로 보존한다.
- `POST /api/v1/events/{eventId}/operation-cases/{caseId}/result`: 저장된 답을 바탕으로 제안을 생성한다. 답이 없으면 409, 이미 완료된 결과는 그대로 반환한다. 실패 후 동일 경로로 재시도할 수 있으며 다시 질문하지 않는다.

사례 객체: `{id,eventId,clientRequestId,situation,questionStatus,action,resultStatus,result,error,createdAt,modifiedAt}`. `action`은 기존 ActionOut이며 선택한 `resolvedChoice`/`manualValue`와 options로 원답 및 선택 label을 복원한다. 질문 상태는 `PENDING`, `PROCESSING`, `NEEDS_ANSWER`, `NO_QUESTION`, `FAILED`, 결과 상태는 `NOT_REQUESTED`, `PROCESSING`, `READY`, `FAILED`. `result`는 `{summary,suggestions}` 또는 null이고 `error`는 안전한 `{code,message}` 또는 null이다. PENDING/PROCESSING은 질문·답변 생성 성공을 뜻하지 않는다. AI 오류는 저장된 사례와 FAILED로 표시하며 사용자의 상황 또는 이미 저장된 답은 삭제하지 않는다.

동일 생성 요청은 처리 중에도 기존 사례를 반환한다. 질문·결과 실행 재요청이 처리 중이면 409 `OPERATION_IN_PROGRESS`. 저장 직후 중단되어 `PENDING`이면 질문 재시도로 복구한다. 일정 시간 이후 재시도는 이전 시도를 무효화하며 늦게 도착한 이전 결과를 저장하지 않는다. AI 호출 전후 소속과 행사 상태를 재확인한다. 권한 없음 403, 다른 행사에 속한 사례/없는 사례 404, 진행 중이 아닌 행사나 답변 전 결과 요청은 409, 입력 형식 오류는 422. 모델 출력은 검증하며 오류 세부나 비밀은 클라이언트에 전달하지 않는다. 입력과 결과는 사용자 데이터이며 외부 지시로 취급하지 않는다.
