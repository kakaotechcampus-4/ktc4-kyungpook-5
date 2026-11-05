# #325 P2 제품 구현·검증

2026-11-05. 기준 `origin/develop` `af8e492`, 구현 브랜치 `codex/325-p2-plan-review`.
기존 `codex/266-planning-progress` 작업 공간은 수정하지 않았다. 미커밋 설계 문서는 `planning-flow-ux-shape.md`로, 당시 PRODUCT.md는 `planning-p2-handoff-product.md`로 보존했다. 현재 제품 공통 PRODUCT.md는 develop 내용을 유지하면서 합의한 P1/P2 관계만 추가했다.

## 제품 동작

- `/planning?eventId=…&stage=review`: 저장된 초안을 P2로 연다. stage 없는 링크는 포함 단계가 있으면 review, 없으면 conditions로 정규화한다. 초안 없는 review 링크는 P1로 안내한다. 진행 중·완료 행사는 기존 행사 상세로 연결한다.
- 명시적인 행사 조건 수정은 `stage=conditions`로 이동한다. 기존 초안은 유지하고 ‘기존 초안 검토하기’로 돌아온다. 새 계획의 최초 대화 뒤에는 conditions에 머문다. 생성 완료 자동 전환은 #326 범위다.
- 행사 목록→상세 경로는 유지한다. 계획 중 상세의 ‘계획 이어보기’가 같은 eventId의 계획으로 연결된다.
- P2 본문은 카탈로그 code로 묶고 서버 배열 순서를 유지한다. 단계 이름·일정/미정·담당·실제 Action 제목을 표시한다. 알 수 없는 code는 기타 단계에 표시한다.
- 미포함 목록은 현재 13개 카탈로그와 저장된 포함 목록의 차이다. 초기 AI 이유는 현재 미포함인 항목에만 ‘AI가 처음 제외한 이유’로 표시한다. 과거 제외 주체나 재생성 영구 보존을 약속하지 않는다.
- 읽기 전용 이전 대화는 서버의 메시지만 표시한다. 입력·전송·빠른 답변·임시 작업 줄이 없다. dialog의 포커스 가두기·Escape·닫기 뒤 복귀를 사용한다.
- 오른쪽은 확인할 점→계획 요약→운영 시작 순서다. 요약은 서버가 제공한 네 단계 수만 사용한다. 생성 경고/검토 중/최신 의견/과거 검토/실패/재검토는 기존 버전 판정과 mutation을 사용한다.

## 두 편집 경로

1. **일정·내용 수정**: 기존 StepDetailModal과 PATCH Step/Action을 재사용한다. 편집을 열 때의 스냅샷을 유지하고 날짜 역전을 요청 전에 막는다. 저장 뒤 해당 P2 버튼으로 포커스가 돌아온다. 여러 요청 중 일부만 성공하면 기존 PartialPlanSaveError로 저장된 항목을 설명한다. 실패 뒤 오래된 버전으로 반복 저장하지 않고 최신 내용을 다시 불러오게 한다. 요청 중에는 모달 닫기를 막는다.
2. **단계 구성 변경**: 기존 `/planning/steps`와 revision 기반 PATCH를 사용한다. 포함·제외·다시 포함·같은 묶음 내 순서만 수정한다. 손잡이는 Pointer Events로 마우스/터치를 처리하고, 재배치로 캡처가 풀리지 않도록 움직이지 않는 상위 영역이 포인터를 캡처한다. 다른 묶음/영역 밖 드롭·pointercancel·Escape는 취소한다. 키보드는 Space/Enter→위아래→Space/Enter, Escape 취소이며 재배치 중 포커스를 유지한다. 구성 저장 전에는 서버 순서를 바꾸지 않는다. 저장 중 컨트롤을 잠근다. 제외 시 일정·작업 삭제 확인, 최소 한 단계, 버전 충돌 복구와 기존 자동 AI 검토 요청을 유지한다. P2에서 진입하거나 eventId로 직접 편집기를 열면 같은 P2로 저장/취소 복귀한다. 명시적인 기존 `from=event`는 상세 복귀를 유지한다.

## 실제 검증

제품 UI `127.0.0.1:5175` → 별도 FastAPI `127.0.0.1:8005` → 전용 PostgreSQL `unyounghae_p2_325`를 사용했다. 기존 서버/DB는 변경하지 않았다. 전용 계정·동아리·행사와 모든 조건은 합성 데이터다. 토큰과 로컬 환경 파일은 Git에 포함하지 않았다.

- FE 빌드·린트 통과, Node 회귀 테스트 **112 passed**.
- BE 실제 PostgreSQL 통합 테스트 `test_events_planning.py`, `test_plan_review_api.py`: **35 passed**. 이 기존 회귀 테스트는 모델 응답을 고정해 저장·동시성·검토 계약을 검증한다.
- 실제 브라우저 E2E: 상세 저장→P2→새로고침, 취소, 날짜 역전, Step 버전 충돌, 일정 성공 뒤 Action 충돌의 부분 저장, 최신 내용 복구를 확인했다. HTTP 응답을 흉내 내지 않고 별도 API 요청으로 실제 버전을 올려 충돌시켰다.
- 구성의 마우스·CDP 터치·키보드 정렬, Escape/그룹 밖 드롭 취소, 구성 저장/변경 취소, 구성 버전 충돌, 제외 확인 취소/승인, 삭제 후 재포함의 새 ID·빈 일정·기본 작업을 확인했다. 저장 뒤 P2와 새로고침에서도 서버 값이 유지됐다.
- 읽기 전용 대화의 입력 부재·Escape 후 포커스 복귀, 조건↔기존 초안, 상세↔같은 eventId 계획, 초안 없는 직접 링크, 직접 링크/새로고침 시 생성 API 미호출을 확인했다.
- 실제 1개/13개 단계, 일정 미정, Action 없는 단계와 320/390/1024/1280/1440px를 렌더링했다. 문서 너비 기준 가로 넘침이 없었다. 물리적인 맥북/터치 기기를 사용한 검증은 아니다.
- 실제 AI 재검토는 `DONE / issues`를 반환하고 DB에 저장됐다. 운영 시작은 실제 `ON_GOING` 전환과 같은 행사 상세 이동을 확인했다. 전용 fixture의 행사 시작일을 비워 실제 `PLAN_INCOMPLETE` 409와 실패 안내도 확인했다. 외부 발송·이체는 하지 않았다.
- 미래 code, 긴 검토 의견, 검토 실패/오래된 결과의 브라우저 경계 검증은 **응답 fixture**로 분리했다. 실제 모델 결과나 DB enum 확장으로 기록하지 않는다.

## 모델 생성 검증의 한계와 계약

실제 합성 조건으로 기존 대화 API 호출은 성공했다. 기존 `mlapi.run` / `gpt-5.6-luna` 생성 호출 두 번은 모두 `validate_plan / invalid_plan`으로 실패했다. 생성 구현을 이 PR에서 바꾸지 않았다. 따라서 생성부터 저장까지 모델 성공을 확인했다는 주장은 하지 않는다. P2 검증용 13단계는 기존 구성 저장 API로 실제 DB에 저장했고, 검토 기준은 기존 `reset_baseline` 서비스로 초기화한 fixture다. 이후 편집·검토·시작은 실제 제품 API로 검증했다. #326의 생성 전환 검증 시 이 생성 실패를 재현·확인해야 한다.

#316의 운영 시작 확인창·재생성 확인은 develop에 아직 없다. #325 범위대로 기존 시작 mutation을 사용하며 P2에 실패 안내와 별도 실행 승인 설명을 연결했다. 확인창 신규 구현은 추가하지 않았다. PR #220은 아직 open이고 base가 `fe/UX_improvement`여서 develop의 재생성 보호로 간주하지 않았다. #324/#328 조건 불일치·교체 보호, #323 P1 카드 정리, #327 생성 중 대화 복귀도 이 변경에 포함하지 않았다.

## 화면 증거

모두 합성 데이터다. `evidence/325/`의 실제 UI/DB 화면과 이름에 `fixture`가 붙은 응답 경계 시나리오를 구분한다.

- [노트북 P2](evidence/325/p2-1280.png), [좁은 P2](evidence/325/p2-390.png)
- [읽기 전용 대화](evidence/325/p2-conversation-readonly.png)
- [상세 충돌](evidence/325/p2-detail-version-conflict.png), [부분 저장](evidence/325/p2-detail-partial-save.png)
- [구성 변경](evidence/325/p2-configuration-laptop.png), [구성 충돌](evidence/325/p2-configuration-version-conflict.png), [좁은 구성](evidence/325/p2-configuration-320.png)
- [제외 후 저장](evidence/325/p2-excluded-saved.png), [1개 단계](evidence/325/p2-single-stage.png)
- [실제 AI 검토](evidence/325/p2-review-result.png), [운영 시작 실패](evidence/325/p2-start-failure.png)
- [긴 검토·미래 code 응답 fixture](evidence/325/p2-long-review-unknown-code-fixture.png), [검토 실패 응답 fixture](evidence/325/p2-review-failure-fixture.png)

## E2E 재실행

`fe/tests/e2e/p2-review.mjs`는 전용 합성 DB에 저장된 13개 단계의 PLANNING 행사에서 시작한다. 테스트는 해당 행사를 수정하고 합성 행사를 추가한다. 실제 데이터가 있는 환경에 실행하지 않는다. `P2_TEST_SESSION`은 `{ "token": "테스트 토큰", "clubId": "…", "eventId": "…" }`인 로컬 JSON 경로다. 토큰 파일을 커밋하지 않는다. Playwright를 설치한 환경에서 실행한다.

```sh
P2_TEST_SESSION=/tmp/p2-session.json node tests/e2e/p2-review.mjs
```

필요하면 `P2_UI_ORIGIN`, `P2_API_ORIGIN`, `P2_EVIDENCE`, `PLAYWRIGHT_MODULE`, `P2_BROWSER_PATH`로 로컬 주소·출력·런타임을 지정한다. `p2-review-boundaries.mjs`는 시작 실패용 fixture(현재 조건에는 날짜가 있으나 행사 테이블 시작일은 NULL)와 응답 경계값을 따로 확인한다. 검토 상태의 API/DB 계약은 위 BE 회귀 테스트도 함께 실행한다.
