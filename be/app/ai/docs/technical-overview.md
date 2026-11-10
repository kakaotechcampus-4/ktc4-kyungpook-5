# 운영해 AI 기술 문서

> 작성 중인 문서입니다. 화면과 기능 소개는 [AI README](../README.md)에 있습니다.
> 이 문서는 토리가 **무엇을 스스로 판단하는지**, 그 판단을 **어떻게 구현하고 검사하는지**, **어떤 근거로 그렇게 정했는지**를 설명합니다.

<!--
작성 규칙 (다음 세션용 메모, 완성 후 삭제)
- 아래 ## 와 ### 제목은 README가 링크로 가리키므로 바꾸지 않는다. 바꾸면 README 링크도 함께 고친다.
- 중간점과 em dash 문자를 쓰지 않는다. AI 티 나는 표현을 피한다.
- 형식 참고: FE 기술 문서 fe/docs/technical-overview.md (PR #399)
- 숫자에는 조건(합성 대본인지, 몇 번 쟀는지)을 짧게 붙인다. 근거는 docs/*-evaluation.md
-->

## 1. 한눈에 보기

AI는 별도 서버가 아니라 BE 프로세스 안의 `be/app/ai` 패키지입니다. BE 서비스가 `from app import ai`로 공개 함수를 부르고, AI는 BE의 DB나 서비스 코드를 import하지 않습니다. 기록 검색이나 진행 알림처럼 BE 기능이 필요하면 BE가 `ports.py`의 인터페이스를 구현해서 넘겨 줍니다.

<p align="center"><img src="images/overview-structure.png" alt="FE, BE, app.ai, 외부 모델의 관계" width="100%" /></p>

### 언제 불리나

| 화면 | 이럴 때 | AI 함수 |
| --- | --- | --- |
| P1 행사 계획 | 메시지를 보내거나 「흐름 만들기」를 누를 때 | `chat_planning`, `generate_planning_preview` |
| P2 계획 검토 | 고친 계획의 검토를 요청할 때 | `review_plan_edit` |
| 회의 | 발화 하나가 받아 적힐 때마다 | `judge_utterance` 외 2개 (함께 시작) |
| 회의 정리 | 회의가 끝난 뒤 | `generate_meeting_review` |
| 자료함 | 파일을 올리거나 검색할 때 | `index_record`, `search_related_records` |
| 메인 화면 | 토리에게 말을 걸 때 | `classify_tori_intent` 외 2개 |
| 행사 운영 | 현재 단계가 바뀔 때, 상황을 물을 때 | `draft_action_content`, `respond_operational_situation` |
| 회계 | 영수증을 올릴 때 | `extract_receipt` |

부르는 BE 서비스와 공개 이름 전체는 [3절](#3-구조)에 있습니다.

### 그림 읽는 법

4절의 흐름 그림은 색이 **누가 정하는지**를 뜻합니다.

| 색 | 뜻 | 예 |
| --- | --- | --- |
| 🟧 주황 | 모델이 판단 | Jev 확률, 도구 선택, 검색어, 본문 작성 |
| 🟦 파랑 | 코드가 검사 | 0.35 기준, 출처 연결, 숫자 대조, 계획 검증 |
| 🟩 초록 | 사람이 결정 | 근거 카드 확인, 초안 확정, 공지 승인 |
| ⬜ 회색 | BE가 처리 | 음성 인식, 청크 검색, 저장 |

점선 알약은 흐름이 멈추거나 사람에게 돌아가는 지점이고, 파란 작은 표시(「한 턴에 최대 3번」, 「한 번만」)는 반복 횟수의 상한입니다. 위의 전체 구조 그림만 예외로, 색이 위치(BE, AI 모듈, 외부 모델)를 뜻합니다.

## 2. 토리가 스스로 하는 일

<!--
README 「토리가 알아서 하는 일」 표를 자세히: 기능별로 움직이는 때, 스스로 고르는 것, 코드가 검사하는 것, 운영진이 정하는 것
실제 판단 기록을 근거로 붙인다
- 회의 6발화 판단 기록(확률, 검색어, 결과, judge_ms)
- 계획 대화 두 번에서 토리가 고른 도구 순서(첫 번째 조건 변경, 두 번째 기록 검색)
행사 Agent 상시 대기는 설계 단계라는 점은 여기서 짧게 밝힌다 (README에서는 뺐음)
-->

## 3. 구조

<!-- 1절에서 넘긴 것: 기능별 부르는 BE 서비스 표(planning_service, plan_review_service, context_service→meeting_ai_service/meeting_event_service, meeting_review_service, record_service, record_discovery_service, routers/tori.py, action_draft_service, operation_cases, accounting_service)와 공개 이름 전체.
공개 경계(__init__.__all__, facade, contracts, ports), 대화 상태 이어가기(state_codec, 이력 60개), 진행 신호(PlanningProgressPort, SSE), 오류 타입(docs/errors.md), 모델 생성은 llm.py에서만 -->

## 4. 기능별 구현

### 4.1 행사 계획 Agent

<!-- LangGraph agent ↔ tools 반복(한 턴 도구 최대 3번), 도구 4개(update_event_conditions, search_past_events, update_generation_offer, generate_event_plan), 생성 그래프 compose_plan → validate_plan(자동 재시도 없음, 실패 이유 반환), 13단계 카탈로그, P2 수정 검토 -->

### 4.2 회의 판단

<!-- Jev 확률 → 0.35 이상이면 luna로 검색어 → find_chunks → assess_chunks → 카드 문구. 앞 발화 4개, 회의 날짜, 제한 시간 10초, 동시 처리 4개, 늦은 답도 띄움, 판단 기록(trace, judge_input) -->

### 4.3 기록 검색

<!-- 청킹 규칙(문서: 쪽과 조항, 장부: 행 1,000자), 임베딩 1536차원, 검색어 정리, 근거 판단, 출처 번호를 코드가 바꿈, 기록 속 지시문 차단, 숫자 검사(#383) -->

### 4.4 공지와 발송 초안

<!-- 신호 A(단계가 현재 단계가 됨), draft_action_content, 요일을 코드가 계산, find_draft_violations, 한 번만 다시 쓰기, [ ] 자리표시 -->

### 4.5 메인 대화

<!-- 의도 분류(record_search, task_list, briefing 등), 답은 DB 값으로, 모호하면 되묻기, redirect 화면 안내 -->

## 5. 숫자로 내린 결정

<!--
README에는 Jev 하나만 남겼다. 여기에는 전체를 「문제, 원인, 고른 방안, 결과, 한계」 순서로
- Jev 전체(미리 정한 기준 3개, 받아들인 1건, 남은 위험)
- 계획 생성 추론 깊이 low: 생성 호출 p50 15.4초 → 11.1초 (#264)
- 생성 출력에서 취소 단계 코드 막음: 채팅 생성 검증 통과 25/30 → 30/30 (#276)
- 기록 재검색 끔: 틀린 사실 12.3 → 6.7, 질문당 1.9초 단축 (#72)
- 검색어 정리: Hit@1 0.41 → 0.58 (#72)
- 회의 검색어 앞 발화 4개: 대상 포함 35~40% → 100%
- 대화 입력 캐시(#269), 한 응답에 도구 여러 개(#265, #274), 날짜 보류 17/30 → 0/30(#205)
-->

## 6. 재는 방법과 평가 세트

<!-- 한 번에 하나만 바꿈, 번갈아 재서 순서 효과 제거(#111), 홀드아웃은 한 번만, 평가 세트 위치(tests/fixtures/eval), 측정 스크립트(scripts/) -->

## 7. 한계와 다음 일

<!-- 행사 Agent 상시 대기 미구현, 0.35 근처 확률 흔들림, 긴 대화 압축 없음(#195), 다시 쓰기 경로 실제 모델 미확인 등 -->
