# #326 공통 생성 화면·저장 확인·P2 연결

2026-11-05. 사용자 확인을 받은 [구체화](planning-generation-shape.md)에 따라 FE 범위를 구현했다.
기준은 #331이 머지된 develop `c9feaa0`, 브랜치는 `codex/326-generation-transition`이다.
**FE 연결과 아래 검증을 완료했다. 결과 조회·재생성 보호의 BE 선행 계약은 남아 있어 #326 전체 완료/공개 준비 완료로 선언하지 않는다.**

## 제품 동작

- 버튼은 즉시 요청 확인, 채팅은 기존 상담/검색을 유지하다 실제 `generation_started`에서 공통 생성 화면으로 바뀐다. 제목·두 단계 안내·토리·기존 색과 타이포, P2 디자인을 유지한다.
- 콘텐츠만 교체한다. `Conversation/usePlanningChat`은 스트림을 계속 받으며 후속 답변과 최종 done을 처리한다. `generation_finished.failed`도 최종 실패로 확정하지 않고, 같은 스트림에서 다시 시작되면 실제 이벤트에 따라 생성 중으로 돌아간다.
- done의 generated 결과와 새 저장 단계의 일관된 snapshot을 함께 확인한 뒤 같은 eventId의 P2로 replace 이동한다. 생성 전 baseline보다 planRevision이 증가하고, done과 baseRevision이 같으며, 새 단계 ID가 이전 ID와 겹치지 않아야 한다. screen과 steps의 두 revision도 일치해야 한다.
- P2 행사 제목에 포커스를 옮기고 완료 낭독을 한 번 표시한다. 라우트의 일회성 안내 상태는 소비해 새로고침에서 반복하지 않는다. 최신 버전 변경을 사용자가 열 때는 이번 생성의 완료로 알리지 않는다.
- 추가 질문/명시적 생성 실패는 P1 안내와 입력창 복귀를 제공한다. 저장된 기존 초안을 유지하며 서버의 사용자용 실패 이유를 표시한다. 저장 거절은 저장된 계획 GET 복구를 제공한다.
- 저장은 성공했지만 GET이 실패한 경우와, GET에 옛 단계/빈 목록이 온 경우를 구분한다. ‘초안 다시 불러오기’는 GET만 수행한다. 새로고침에도 저장된 done 결과와 확인 목표를 유지한다.
- 연결/응답 파싱/불명 오류에는 그 행사의 새 요청을 잠근다. 같은 키 POST도 자동 반복하지 않는다. 대신 `GET /events/{id}/plan/requests/{key}`로 결과만 조회해 저장됐으면 이어 가고, 처리 중이면 3초마다 다시 조회하고, 저장되지 않았으면 잠금을 풀고 원래 문장을 입력창에 되돌린다(#342). 탭 기록은 행사마다 따로 두어 다른 계획은 잠그지 않는다.
- 탭 기록은 사용자·동아리·행사·원래 경로 종류·정확한 본문·멱등키·기준 revision/단계 ID를 보관한다. 토큰을 넣지 않는다. 완료 후 지우며, 새 요청의 기록을 오래된 요청이 지우지 못하게 한다. 저장 기능을 쓸 수 없으면 첫 POST도 보내지 않는다.
- 다른 행사/라우트로 이탈한 뒤 늦게 완료돼도 현재 화면을 이동시키지 않는다. 현재 요청이 있는 동안 계획 선택·새 계획·전송·생성을 잠근다. 화면/주소 진입 자체는 생성하지 않는다.

주요 코드: `generation.ts`(판정·탭 기록), `useGenerationRequest.ts`(수명·저장 조회),
`hooks.ts`(원래 두 스트림), `stream.ts`(단일 POST·terminal 응답 검증),
`GenerationScreen.tsx`, `GenerationFailureNotice.tsx`, `LivePlanning.tsx`, `PlanReviewScreen.tsx`.

## 검증 환경과 구분

별도 FE `127.0.0.1:5176` → 검증 전용 임시 Vite 프록시 → 기존 전용 BE `127.0.0.1:8005` →
PostgreSQL `127.0.0.1:5434/unyounghae_p2_325`에서 **새 합성 행사**로 확인했다.
BE 프로세스의 연결 DB 이름을 비밀값 출력 없이 확인했다. 기존 #325 행사 데이터는 수정하지 않았다.
추가한 fixture용 빈 행사와 실제 모델 생성 행사는 합성 검증 동아리 안에서만 만들었다.
BE·AI·스키마·모델 설정·기존 사용자 DB를 변경하지 않았다. 임시 프록시/토큰/환경 파일은 커밋하지 않는다.

프록시는 새 FE 포트를 기존 BE CORS 설정에 추가하지 않기 위한 로컬 검증 설정이다.
배포 설정이나 제품 API 변경을 뜻하지 않는다. 로컬 개발 서버는 이번 worktree를 사용하며, 배포는 수행하지 않았다.

## 실제 모델 → HTTP/SSE → DB → P2

기존 mlapi.run / `gpt-5.6-luna`와 현재 프롬프트·검증 규칙을 그대로 썼다.
아래 두 성공 초안은 구성 API로 만든 #325 fixture와 다르며, 실제 모델 생성 결과가 저장된 것이다.

| 경로 | 합성 행사 | 실제 저장 결과 | 브라우저 확인 |
| --- | --- | --- | --- |
| 버튼 | `evt_miZe1bwwXdMFUoiSpdTYg` | 12단계, baseRevision 2 / planRevision 2 | generation_started → 대기 → done generated → 새 snapshot → P2, 생성 POST 1회, 제목 포커스, 새로고침 후 유지·추가 POST 없음 |
| 채팅 | `evt_h9p123wOSHcInshwgXhVD` | 12단계, baseRevision 2 / planRevision 2 | 생성 권유 뒤 동의 → 실제 generation_started → 같은 대기 → 저장된 새 P2, 해당 채팅 POST 1회, 제목 포커스, 새로고침 후 유지·추가 POST 없음 |

[실제 경로 요약](evidence/326/verification-real.json).
버튼 성공은 첫 실제 실행에서 관찰했고, 이후 채팅 테스트의 시간 제한 실패 때문에 보존 요약에 해당 관측과 DB GET 확인을 함께 명시했다.

별도 합성 행사 `evt_uxi0wmCsvHqNYFEPuCIAg`에서는 보류 뒤 생성 요청에 토리가 재확인을 물었다.
실제 시작 이벤트가 없어 P1을 유지했다. 다음 동의 요청은 12단계를 실제 저장했으나 브라우저 관측의 30초 제한에 걸려
전체 대기→P2 증거로 세지 않았다. 같은 요청을 재전송하지 않고 GET으로 저장 결과만 확인했다.
위의 새 채팅 행사에서는 충분한 관측 시간으로 전체 흐름을 확인했다. 테스트 시간 상한을 사용자용 완료 타이머로 구현하지 않았다.

## 고정 응답·경계 검증

모델 응답이나 실 DB 저장을 통과한 것으로 해석하지 않는 **별도 SSE/HTTP fixture**다.
실제 브라우저에 SSE를 나눠 보내 사용자가 각 상태를 보는 동안 다음 이벤트를 수동으로 진행시켰다.

- **12개 시나리오 통과**, 브라우저 JavaScript 예외 0. [요약](evidence/326/verification-fixtures.json).
- 버튼 요청 확인→시작→결과 확인→P2; 내부 생성 실패 이벤트 뒤 재시작→완료도 단일 POST 유지.
- 채팅 상담·검색에서는 생성 화면이 없고 실제 생성 시작 때만 전환. 추가 질문과 명시적 생성 실패에서 P1 복귀·이전 초안 유지·입력창 포커스 확인.
- 저장 버전 충돌 안내와 ‘저장된 계획 다시 확인’의 GET 복구. 생성 재전송 없음.
- done generated 후 GET 500 또는 옛 snapshot→실패 화면→새로고침→GET 재시도→P2. 각 생성 POST는 1회.
- 더 최신 버전이면 자동 성공 대신 현재 계획 보기. 완료 낭독을 만들지 않고 replace 이력 길이 유지.
- 연결 단절→결과 불명→새로고침에서도 잠금, POST 1회. 예상한 테스트 연결 단절은 `ERR_INCOMPLETE_CHUNKED_ENCODING`으로 관측됐고 제품은 불명 상태로 처리했다.
- SPA에서 다른 행사로 이탈한 뒤 완료돼도 새 행사를 이동시키지 않음. 원래 행사로 명시 복귀해 저장 결과 GET만으로 P2 진입.
- 임시 저장 불가 시 POST 0회. 빠른 두 번 Enter에도 생성 POST는 1회.

FE lint/build 통과. Node 테스트 **119 passed**(기존 112 + 생성 계약 7).
새 테스트는 이전 단계/빈 단계/중복 ID/다른 revision의 성공 오인, 손상된 탭 기록·범위 분리·오래된 정리,
단절 시 POST 반복 방지, done 뒤 전송 단절, 잘못된 JSON/불완전 done을 검증한다.
빌드의 기존 500KB 이상 번들 경고는 남아 있다. 이번 작업에서 별도 번들 분할은 하지 않았다.

## 화면·접근성 증거

모두 합성 데이터이며 파일명 `real-`과 `fixture-`를 구분한다.

- 실제 생성: [버튼 대기](evidence/326/real-button-generating-1280.png), [버튼 P2](evidence/326/real-button-p2-1280.png), [채팅 대기](evidence/326/real-chat-generating-1280.png), [채팅 P2](evidence/326/real-chat-p2-1280.png).
- 상태: [요청 확인](evidence/326/fixture-requesting-1280.png), [생성 결과 확인](evidence/326/fixture-verifying-1280.png), [저장 후 조회 실패](evidence/326/fixture-read-failure-1280.png), [옛 단계 거절](evidence/326/fixture-stale-snapshot-1280.png), [생성 실패](evidence/326/fixture-generation-failed-1280.png), [저장 충돌](evidence/326/fixture-save-conflict-1280.png), [결과 불명](evidence/326/fixture-unknown-1280.png).
- 반응형: [1440](evidence/326/fixture-generating-1440.png), [노트북 1280](evidence/326/fixture-generating-1280.png), [1024](evidence/326/fixture-generating-1024.png), [390](evidence/326/fixture-generating-390.png), [320](evidence/326/fixture-generating-320.png).

CSS viewport 높이는 800px이며 캡처는 fullPage다. 좁은 화면은 세로 스크롤을 허용하고 가로 넘침은 없다.
대기 제목 포커스, 질문/실패 안내 포커스→입력창 복귀, Enter 복구, P2 제목 포커스와 새로고침 후 중복 완료 알림 부재를 자동 브라우저에서 확인했다.
`prefers-reduced-motion: reduce`에서는 진행 표시의 computed animationName이 `none`이다.
실물 맥북/터치 기기나 VoiceOver를 사용한 검증은 아니며, 실제 낭독 품질까지 검증했다고 주장하지 않는다.

## 남은 BE 계약과 범위

1. **읽기 전용 요청 결과 조회**: #342에서 추가했다. 턴 저장과 키 완료를 한 커밋으로 묶어 "저장됐는데 처리 중" 기록이 생기지 않는다. 서버가 처리 도중 꺼지면 그 행사는 최대 5분 동안 확인 중으로 남는다. 탭 기록 삭제·다른 기기·새 탭까지 FE 잠금이 보호하지는 않는다.
2. **양 경로 재생성 교체 동의**: 착수 시 #220은 open, base `fe/UX_improvement`였다. 현재 기반에는 보호 계약이 없다. 기존 API 요청 값을 덮어쓰거나 자동 재전송하지 않았으며, 모달만으로 채팅 교체까지 보호했다고 보지 않는다. 보호된 재생성의 제품 공개는 #316/#220와 양 스트림의 연결 확인 뒤에 판단한다.
3. **invalid_plan**: 선행 #325의 두 실패는 여전히 정확한 rule/path 미확보다. 이번 AI 함수 진단 5회와 실제 생성에서 동일 실패가 재현되지 않았다. 검증 완화·모델/프롬프트 교체·실패 성공 처리로 우회하지 않았다. 새 실제 실패가 나오면 기존 구조화 수집기로 해당 첫 위반을 확보해야 한다.

#323 P1 전체 카드 정리, #324/#328 조건 일치 표시, #327 생성 중 대화 복귀와 전체 요청 복원,
#316 운영 시작 확인창은 추가 구현하지 않았다. 이 변경으로 해당 작업을 완료 처리하지 않는다.

## 다시 실행하기

전용 합성 API/DB와 인증 세션을 준비한 뒤 `fe/`에서 실행한다.
`GENERATION_TEST_SESSION`은 `{ "token": "검증 토큰", "clubId": "검증 동아리" }`인 Git 밖 JSON 경로다.
브라우저 런타임은 `PLAYWRIGHT_MODULE`/`P2_BROWSER_PATH`, 로컬 주소는 `GENERATION_UI_ORIGIN`/`GENERATION_API_ORIGIN`으로 지정할 수 있다.

```sh
node --test tests/*.test.mjs
GENERATION_TEST_SESSION=/tmp/326-session.json node tests/e2e/generation.mjs
GENERATION_REAL=1 GENERATION_FIXTURES=0 GENERATION_TEST_SESSION=/tmp/326-session.json node tests/e2e/generation.mjs
```

실제 모델 검증은 새 합성 행사를 만들며 유료 모델을 호출한다. 기본 브라우저 시나리오는 고정 응답이며 새로운 빈 합성 행사만 만든다.
임의의 실제 동아리 데이터 환경에서 실행하지 않는다.
