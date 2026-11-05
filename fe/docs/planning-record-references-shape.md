# 행사계획 P1 · 참고한 과거 기록

기준일: 2026-11-05 (Asia/Seoul). 상태: 현재 구현과 로컬 검증 범위.

운영진이 **어떤 사실을 어느 문서의 어디에서 확인했는지** 검토하고 원본을 내려받는다. 올해 조건은 기존 대화로 정한다. 별도 조건 반영 버튼, 앱 내 PDF·시트 뷰어, 메시지별 출처 연결은 포함하지 않는다. 기존 제품의 토큰·Card·Button·타이포·중립색·토리 블루를 유지하는 화면 확장이다.

## 화면과 정보 위계

- `LivePlanning`은 **지금까지 정한 것 → 계획 초안 생성 → 참고한 과거 기록** 순서로 배치한다. 1280px 이상(`xl`)은 채팅과 오른쪽 340px 열의 두 열이며 채팅은 sticky다. 그보다 좁으면 채팅 아래 같은 순서로 쌓는다.
- 참고 카드는 조회 전에도 표시하며 “과거 기록을 찾아보면 여기에 내용과 출처가 남아요.”로 안내한다. 작은 토리와 제목만 남긴 간결한 헤더를 사용하고 반복 안내 문구는 덜어낸다. 기록을 펼쳐도 앞에 있는 초안 생성 버튼이 밀리지 않는다.
- 최근 조회는 펼쳐 보여준다. 사실은 응답 순서대로 1개만 먼저 표시하며 나머지는 “확인한 내용 N개 더 보기”로 펼친다. 150자를 넘는 사실은 기본 3줄과 “전체 내용 보기”를 제공하고 펼치면 전문을 읽는다.
- 사실마다 출처를 연결한다. 출처 하나는 파일명·위치·원본 다운로드를 바로 보여주며, 여러 개는 native `details`의 “출처 N개 보기”로 펼친다. 파일명과 위치는 줄바꿈하며 임의로 요약하지 않는다.
- 이전 조회는 기본 접힌 native `details` 안에 보관한다. 개별 조회도 접혀 있고, 처음 5건 이후 한 번에 최대 5건씩 더 표시한다. 최신 실패가 와도 이전 성공은 이 목록에서 다시 확인할 수 있다.
- 헤더 자료 수는 **전체 조회 이력의 facts 및 conflicts.values 출처에서 recordId 고유 개수**로 센다. 같은 사실의 출처 행은 `recordId + location.label`로 중복 제거한다. 문서 수와 조회 수는 서로 다르다.
- `notFound`는 “확인하지 못한 내용”, `conflicts`는 “기록마다 내용이 달라요”로 구분한다. 미확인 목록과 서로 다른 값의 상세는 기본 접힘이며, 최신 충돌의 “내용 차이 있음” 표시는 유지한다. 어떤 값도 FE가 정답으로 선택하지 않는다. 조회 시각·관련도·신뢰도·자료 연도를 만들거나 Tool 입력 `query`를 사용자 발화처럼 노출하지 않는다.

## 상태와 복원 계약

| 입력/상황 | 현재 동작 |
| --- | --- |
| 저장된 조회 없음 | 카드와 조회 전 안내 표시. 업데이트용 live region도 마운트 유지 |
| 이번 턴 `recordLookup=null` | 기존 최근 조회와 이력 유지 |
| 새 `available` | 최근 조회로 표시하고 이전 조회 보관 |
| 새 `not_found` | “이번 조회에서 관련 내용을 찾지 못했어요.”와 자료함 링크. 이전 성공은 이전 조회에만 표시 |
| 새 `failed` | “기록을 불러오지 못했어요. 잠시 후 대화에서 다시 요청해 주세요.”. 이전 이력 유지 |
| 새 `rejected` | 진행하지 못한 상태와 사용자용 reason 표시 |
| 옛 `available`, `result=null` | “이 조회는 상세 출처가 저장되어 있지 않아요.”. 자료 없음으로 해석하지 않음 |
| 전체 채팅/저장 실패 | 저장된 조회 보존. 기존 채팅 오류 영역에서 처리 |
| 재접속·새로고침 | GET의 저장 스냅샷으로 복원. AI 재호출 없음 |

BE는 `Conversation.record_lookup_history` JSONB에 `{revision, lookup}` 목록을 저장한다. 새 조회가 있는 정상 턴은 마지막 조회·조회 이력을 조건·메시지·Agent 이어가기 상태와 같은 트랜잭션에서 저장한다. POST의 이번 턴 `recordLookup`과 GET의 `lastRecordLookup`은 유지하며, GET `PlanScreenOut.recordLookupHistory`가 누적 이력을 제공한다. null 턴은 새 항목을 만들지 않는다.

FE의 `planningRecordHistory()`는 GET 이력과 저장된 POST 결과를 revision 기준으로 합치고 최신순으로 정렬한다. 같은 revision을 중복 누적하지 않고 GET보다 오래된 응답은 채택하지 않는다. 이력이 없고 마지막 조회만 있으면 revision 0의 호환 항목으로 읽는다. 화면 복원을 위해 AI의 비공개 Tool 이력을 분석하지 않는다.

마이그레이션 `be/alembic/versions/20261105_planning_record_history.py`의 revision은 `20261105_planning_history`, 선행 revision은 `20261105_merge_heads`와 `20261105_meeting_review_confirm`다. 기존 마지막 조회만 revision 0으로 옮긴다. 0은 원래 조회 턴을 모른다는 뜻이며, 저장되지 않은 과거 출처나 시각을 복원하지 않는다. 적용 명령은 대상 DB 설정을 확인한 뒤 **`be/` 디렉터리에서** `uv run alembic upgrade head`다. 이번 검증에서는 **격리 테스트 DB에만 적용했으며 사용자·운영 DB는 변경하지 않았다.**

## 원본 접근과 접근성

제품 카드는 기존 `downloadRecord(recordId, fileName)`로 인증된 `GET /records/{recordId}/file`을 호출한다. 계획 화면을 유지하며 브라우저로 원본을 내려받는다. 버튼은 “받는 중…”과 파일별 오류·“다운로드 다시 시도”를 제공한다. 실패 문구는 “파일을 받지 못했어요. 권한과 연결 상태를 확인해 주세요.”이며 파일명은 접근 가능한 버튼 이름에 포함한다. 전달된 위치 label은 받은 파일에서 찾을 단서다. 앱 안에서 PDF 페이지나 시트 행으로 이동하는 기능은 없다.

확장은 native `details` 또는 `aria-expanded`·`aria-controls`가 있는 버튼으로 작동한다. 항상 마운트된 `role=status`, `aria-live=polite`, `aria-atomic=true` 영역은 저장된 조회 수와 최신 결과를 알린다. 새 조회 12→13건에서 문구가 바뀌며, 이전 조회를 펼치는 조작으로 재알림하지 않는다. 다운로드 오류는 해당 행의 alert로 알린다. 색상만으로 실패·충돌을 구분하지 않으며 44px 이상의 터치 영역과 reduced-motion 처리를 사용한다.

`/planning?demo`는 합성 출처로 만든 화면 미리보기다. 출처 행의 “예시 자료” 표시를 사용하며 제품 다운로드를 실행하지 않는다. 실제 인증·검색·저장 검증의 증거와 구분한다.

## 확인한 범위와 한계

2026-11-05 로컬 검증 결과:

| 확인 | 결과 |
| --- | --- |
| BE `tests/unit/test_planning_record_views.py` + `tests/integration/test_planning_record_lookup.py` | 12 passed |
| BE `tests/integration/test_events_planning.py` | 18 passed |
| FE `node --test tests/planning-*.test.mjs` | 최신 develop 통합 후 30 passed |
| FE build / 대상 파일 eslint | 통과. 기존 500kB 초과 chunk 경고 유지 |
| 격리 DB migration / `alembic check` | 적용·이전 데이터 backfill 확인. “No new upgrade operations detected.” |
| 제품 브라우저 흐름 | 실제 HTTP·검색 port·저장소·격리 DB로 13개 누적 조회, 이전 조회/5건 더 보기, 사실/전문 확장, 실패·없음·충돌, 인증 다운로드, 재접속 복원 확인 |
| 반응형과 알림 | 1440·1280·390px에서 가로 넘침 없음. 새 조회 live region 변경과 이력 토글 시 문구 유지 확인 |
| 최종 리뷰 후속 확인 | 누락됐던 조회 결과 live region 보완 확인 후 pass / ship 판정 |

브라우저 흐름은 **합성 파일과 고정 모델·임베딩 응답**을 사용했고 유료 공급자 호출은 하지 않았다. 실제 제품 경로의 연결·상태·복원을 확인한 결과이며 실제 모델 판단, 일반 검색 품질, 사용자 데이터 또는 운영 배포 준비 완료를 뜻하지 않는다. 운영 환경에는 별도 migration 적용과 설정·자료·권한 검증이 필요하다. 임시 검증 서버와 격리 DB 컨테이너는 검증 후 정리했다.

최신 develop 통합 화면과 재현 흐름은 [화면 검증 기록](ui-tests/planning-record-references/README.md)에 보관한다. 통합 후에도 진행 줄·답변 서식·조건 강조·계획 검토를 유지하며, 7건의 성공 조회 뒤 새 검색 실패가 8번째 조회로 저장되고 이전 7건이 남는 것을 제품 스트리밍 경로와 새로고침으로 확인했다. 앞선 단독 구현에서는 별도로 13건 누적과 긴 내용·충돌·자료 없음 상태도 확인했다.

구현 기준: `fe/src/features/planning/{recordReferences.ts,hooks.ts,components/PlanningRecordReferences.tsx,components/LivePlanning.tsx,components/PlanChat.tsx}`, `be/app/{models/chat.py,schemas/events.py,services/planning_service.py}`. AI 검색 정책·생성 정책·기존 디자인 시스템은 이번 화면 확장으로 바꾸지 않는다.

피드백 후 밀도 조정은 변경한 FE 파일의 TypeScript·ESLint 확인만 수행한다. 사용자 요청에 따라 별도 브라우저·DB·회귀 테스트는 반복하지 않는다. 위 표와 화면 증거는 최초 구현·통합 당시 검증 기록이다.
