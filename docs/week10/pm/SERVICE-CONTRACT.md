# 운영해 — 회의·Discord 맥락 보조 API 제안

기준일 2026-10-12. 사용자가 전달한 2026-10-11 회의 결정을 최신 제품 방향으로 반영했다. 프론트와 첨부 ERD에는 아직 반영되지 않았으며, 아래 경로·필드·상태·테스트 지원 API는 모두 구현 합의용 제안이다. 사용자에게서 전달받은 결정 외의 회의 내용을 확인한 것은 아니다.

## 확정된 방향과 이번 제안

| 사용자 전달 결정 | 이번 문서의 구현 제안 |
| --- | --- |
| 회계는 영수 내역 직접 업로드·영수증 OCR로 축소 | 확정 지출과 업로드/OCR 초안을 분리하고 사람이 교정·확정. 자동 수납 대조·송금·환불 제외 |
| 작은 캐릭터로 활동 상태 표시 | snapshot + SSE, 작업별 stage·status·재접속 cursor. 이름·캐릭터 디자인 미정 |
| 회의 음성 STT 후 Jev가 RAG/LLM/NONE 판단, 필요한 도구 호출 | 음성 청크/STT 확정본, 판단 및 정보 조회·답변 생성 이력 분리 |
| Discord 메시지 맥락에서 필요한 할 일 도출 | 허용 채널 수집, 메시지 수정/삭제·근거 버전, 별도 task-suggestions |
| 도출한 할 일을 실제 수행할 범위는 아직 미정 | 수락/거절은 정리 UX 제안, 예약·송금·게시 등 execute API는 추가하지 않음 |

RAG 검색이나 LLM 생성은 필요한 정보 제공을 위한 내부 도구 호출이다. 할 일의 실제 업무 실행과 구분한다. 회계의 수입/환불 기록과 정산 보고서까지 포함할지는 합의되지 않았으므로 이번 핵심 세트는 지출 내역을 다룬다.

## PM 사용 순서

1. `service-flow.curl.sh`: 테스트 계정·동아리·선택 행사 준비.
2. `accounting.curl.sh`: 직접 입력 또는 CSV 업로드, 영수증 이미지 OCR, 검수·확정.
3. `activity.curl.sh`: 작업 시작 전 다른 터미널에서 SSE 연결.
4. `meeting.curl.sh`: 회칙 RAG 자료 준비 → 회의 시작 → 실제 음성 STT 또는 테스트 전사 주입 → Jev 분기 조회 → 종료.
5. `discord.curl.sh`: 테스트 채널 연결 → 실제 메시지 또는 테스트 이벤트 → 맥락 판단 → 할 일 검토.
6. `service-errors.curl.sh`: 별도 데이터로 권한·중복·수정·삭제·실패 테스트.

모두 문서용 shell 파일이며 처음에 `exit 0`이 있다. 필요한 블록만 같은 터미널에 복사한다. source하거나 일괄 실행하지 않는다. 실행 예시는 저장소 루트 기준이다. 응답의 토큰·ID·version을 다음 export에 넣는다. 별도 터미널의 SSE에는 API/CLUB_ID/ACCESS_TOKEN을 따로 설정한다. curl 자체는 녹음 UI나 Discord bot Gateway 소비자를 대신하지 않는다.

## 공통 HTTP 계약

- `/api/v1`, camelCase JSON, datetime UTC ISO 8601, 금액은 정수 원. 단건 성공 `{data,meta:null}`, 페이지 목록 `{data:[],meta:{page,size,totalCount}}`, 실패 `{error:{code,message,fields?}}`, 204 본문 없음.
- 비동기 접수는 202이며 접수 성공만으로 처리가 끝난 것이 아니다. 조회 HTTP는 200이더라도 data.status가 FAILED면 기능 실패다. `agent-jobs`는 QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED와 stage/result/error를 반환한다.
- `agent-jobs` 완료 결과에는 contextDecisionId 또는 receiptImportId 등 결과 리소스를 연결한다. 한 STT 작업에 여러 segment가 생성되면 contextDecisionIds 배열을 반환한다. fixture 단일 segment의 jobId는 단일 contextDecisionId 조회를 가정한다. 실제 STT 결과의 items[].decisionJobId로 자동 판단 job을 이어 조회할 수 있다.
- 원본 입력 source 버전, 모델·정책 버전, attempt, correlationId를 기록한다. 작업 상태, Jev route, 할 일 수락 상태는 서로 다른 값이다.
- 계정과 동아리 멤버십을 구분한다. 모든 리소스 조회/변경·job·SSE·검색은 해당 clubId 접근 권한 검사. OWNER/MANAGER만 자료 확정·연결 변경·제안 수락 가능하도록 제안한다.
- Idempotency-Key의 범위는 사용자+동아리+endpoint. 같은 key/body는 최초 성공 결과를 재사용하고, key/body가 달라지면 409 IDEMPOTENCY_CONFLICT. key와 별도로 소스 ID/버전·import row uniqueness를 DB에서 보장한다.
- `expectedVersion` 충돌 409 VERSION_CONFLICT, 근거 변경 409 SOURCE_VERSION_CHANGED. retry보다 먼저 리소스 재조회. 소스 최신성·수락 갱신은 한 트랜잭션에서 확인한다.
- 권한 실패 401 UNAUTHORIZED/403 FORBIDDEN. 타 동아리 리소스 404 은닉으로 합의할 수도 있다. 잘못된 입력 422 VALIDATION_FAILED.

## 리소스별 계약과 구현 완료 조건

| 리소스/요청 | 응답·상태 제안 | PM 확인/구현 필요 |
| --- | --- | --- |
| `POST /clubs/{id}/expenses` | 201 CONFIRMED, source=MANUAL | 직접 영수 내역 저장, amount 정수·KRW·spentAt, 외부 결제 없음 |
| `POST /clubs/{id}/receipt-imports` | multipart type=EXPENSE_CSV/RECEIPT_IMAGE, 202 id/jobId | 원본 records 연결·파일 형식·내용 해시·업로드자 |
| `GET /clubs/{id}/receipt-imports/{id}` | QUEUED→PROCESSING→NEEDS_REVIEW→CONFIRMED, 실패 FAILED | 원본 OCR/파싱 결과, draft expenseRows, row/field 오류·confidence, version |
| `PATCH .../{id}/draft` | expectedVersion, expenseRows, 200 버전 증가 | 원본 추출값과 사람이 고친 값 분리, CONFIRMED 뒤 초안 수정 차단 |
| `POST .../{id}/confirm` | expectedVersion, 200 expenseIds | 처리 완료+필수값 확인, 확인자/시각, 원자적 저장, 중복 row 확정 금지 |
| `GET /clubs/{id}/expenses[/{id}]` | 확정 내역만, 원본/수정 출처 | 3개 예시 내역 50000원; OCR은 실제 원본 금액으로 별도 확인 |
| `POST /clubs/{id}/meetings` | 201 RECORDING | title/language/recordingConsentConfirmed, eventId 선택 |
| `POST /meetings/{id}/audio-chunks` | seq/startMs/endMs/file, 202 chunkId/jobId | 입력 청크 순서·해시·중복 방지, 같은 seq 다른 음성 409 CHUNK_CONFLICT |
| `GET /meetings/{id}/transcripts?afterSeq=` | 변경 이벤트 cursor + items[] | items는 id, sourceId, sourceVersion, segmentSeq, text, final, speakerLabel, decisionJobId, 시각 포함. afterSeq는 변경 cursor이며 수정도 전달 |
| `POST /meetings/{id}/finish` | 202 FINALIZING→COMPLETED 또는 FAILED | 입력 종료 후 처리 중 음성·미확정 전사를 drain. 늦은 STT는 수용, 새 음성 업로드는 차단 |
| `GET /meetings/{id}` | 회의 상태와 오류/청크·전사 집계 | COMPLETED이면 오류 0인지 별도 판정; 누락을 정상 완료로 표시하지 않음 |
| 자동 `context-decisions` 생성 | 최종 STT/채널 입력 → Jev 판단 job | partial 전사에 정보 도구 호출 금지, 문맥 window·debounce 정책 필요 |
| `POST /clubs/{id}/context-decisions` | sourceType/sourceIds/expectedSourceVersions, 202 jobId | PM 재판단·실패 재시도용. ACTIVE 동일 소스/버전 job 재사용, 이전 실패 attempt 보존 |
| `GET /clubs/{id}/context-decisions[/{id}]` | route/status/reasonCode/toolCalls/output/citations | NONE도 판단 이유·성공 기록. 내부 추론 전문 대신 제품 근거 요약·출처 |
| `POST /clubs/{id}/discord-connections` | guildId/channelIds/botProfile/enabled, 201 | 서버 bot 설정과 채널 권한 사전 준비. bot token은 API/DB 로그에 넣지 않음 |
| `GET/PATCH /discord-connections/{id}` | version, enabled, status, channels, cursor | 허용 채널·중지·연결 단절과 재연결을 구분 |
| `POST /discord-connections/{id}/sync` | 202 jobId | Gateway 연속 수집의 catch-up 보조 읽기. 새 메시지를 외부에 작성하는 API 아님 |
| `GET /discord-connections/{id}/messages` | 내부 id+외부 messageId+sourceVersion+원문 상태 | Discord ID 문자열. 원문 수정/삭제 tombstone·새 검색/근거 무효화 |
| `GET /clubs/{id}/task-suggestions[/{id}]` | PROPOSED/ACCEPTED/DISMISSED/NEEDS_REVIEW | 동아리 공통 가능, eventId 선택. 근거 message/전사 버전 포함, 기존 actions와 분리 |
| `PATCH .../{id}` / `POST .../{id}/accept` / `dismiss` | expectedVersion, status/version, 200 | 명칭·마감 수정, 수락/거절 이력. ACCEPTED는 실제 수행·완료가 아님 |
| `GET /clubs/{id}/activity` | cursor/jobs[]/connections[]/characterState | mini의 상태는 작업 집계, 행사를 실행했다는 뜻이 아님 |
| `GET /clubs/{id}/activity/stream` | SSE id/event/data, Last-Event-ID 재접속 | after cursor 재생, 만료 409 ACTIVITY_CURSOR_EXPIRED → snapshot. heartbeat 별도 |

경로별 기존 구현 여부는 README에 있다. 위 신규 API는 현재 라우터에 없다. 회원 명단·참가 응답·미응답 안내 승인·수동 게시 흐름은 이번 중심 기능의 선행조건으로 넣지 않았다. 기존 기획은 legacy에 보존했다.

## Jev 세 분기 테스트

| 입력 예시 | 기대 route | 하위 도구/결과 |
| --- | --- | --- |
| 회칙에서 행사 취소 공지가 며칠 전인지 질문 | RAG | `records.search`(clubId 강제) → 필요하면 `llm.generate`, 실제 출처·위치와 답변 |
| 모임 장소를 정하자는 문구를 친근하게 바꿔달라는 요청 | LLM | `llm.generate`, 기록 검색 불필요 |
| 잘 들린다는 말·물 마신다는 잡담 | NONE | downstream toolCalls=[], output=null, 판단 기록은 존재 |

route는 처음 필요한 작업의 분류다. RAG 뒤 답변을 정리하는 LLM 호출도 가능하다. NONE은 판단 classifier까지 실행하지 말라는 뜻이 아니다. 도구 timeout/검색 실패를 NONE으로 바꾸지 않는다. 검색 결과 없음은 NOT_FOUND 근거로 안내하며 확인되지 않은 회칙을 만들어내지 않는다.

참고 예시는 인수 기준이며 임의 회의 문맥에서 항상 같은 분기를 보장하는 강제 규칙은 아니다. 고정 fixture 평가 때 준비된 문맥/정책 버전을 같이 기록한다. 실제 구현은 선택한 route만 고정하지 말고 도구 호출/결과/근거도 검증한다.

## 실시간과 테스트 지원 API

- 음성 경로는 실제 테스트 WAV 파일이 필요하다. repo에 녹음 파일·영수증 이미지가 포함되어 있다는 의미가 아니다. 청크 크기·codec·세션 종료 규칙은 구현팀이 정한다. curl 업로드는 전송 계약 확인이며 브라우저 마이크/실시간 STT latency 자체의 전체 검증은 아니다.
- `/test-support/clubs/{id}/meetings/{id}/transcripts`: seq/startMs/endMs/final/text/expectedVersion 입력으로 partial·final·수정 시뮬레이션. 실제 STT worker가 넣는 데이터 형식과 같은 파이프라인을 사용. 응답은 id/version/sourceId/sourceVersion/자동 판단 jobId를 제공한다. 같은 seq 갱신은 expectedVersion 필수.
- `/test-support/clubs/{id}/discord-connections`: 실제 bot credential 없이 mode=FIXTURE 연결을 만든다. 실제 Discord 설치/접속을 검증한 결과가 아니다.
- `/test-support/clubs/{id}/activity-cursors`: state=EXPIRED로 올바른 형식의 만료 cursor를 발급해 409과 잘못된 cursor 형식 오류를 구분한다.
- `/test-support/clubs/{id}/discord-events`: 내부 consumer 메시지 CREATE/UPDATE/DELETE 시뮬레이션. guild/channel/message IDs와 sourceOccurredAt을 사용. 프로덕션에서 공개하는 webhook 경로가 아니다.
- `/test-support/clubs/{id}/failpoints`: 동아리 한정 일회성 도구 실패. 테스트 환경에서만 허용, 초기화 시 해제. 실제 음성 인식·실 Discord 연동 성공과 혼동하지 않는다.
- 모든 test-support는 TEST_MODE=true 및 테스트 운영진 권한에서만 등록한다. 운영 환경 404. 입력 fixture로 route를 지정해 분기를 강제하지 않는다. 오류 테스트에서는 새 RECORDING 회의와 enabled 연결을 준비하며, 한 번만 실패시키는 failpoint를 설정하기 전 앞선 작업 완료를 확인한다.
- Discord 연결을 중지한 뒤 들어온 이벤트를 새로 분석하지 않는다. 이미 시작한 분석은 취소/결과 게시 억제 정책을 정해야 한다. 재연결 시 cursor catch-up·중복 이벤트 방지·원문 편집 시간 역전 처리가 필요하다.
- 원문 삭제/최종 STT 교정은 source version을 바꾼다. 이전 decision은 STALE, 관련 할 일은 NEEDS_REVIEW. 수락된 일을 자동 실행/자동 완료하지 않는다. 원문·음성·임베딩 삭제와 보관 기간도 정한다.
- mini activity는 IDLE/WORKING/ATTENTION 집계 상태를 제안한다. 연결 MONITORING/PAUSED/DISCONNECTED 상태, 작업 stage/status는 따로 표시. 완성된 캐릭터 디자인·애니메이션 이름을 ERD enum으로 고정할 필요 없다.

## 백엔드 작업 순서

1. 공통 DB·동아리 권한·비동기 job·source 버전·activity cursor 계약.
2. 영수 내역 CSV/OCR 파이프라인과 교정/확정 (자동 금융 실행 없음).
3. 회의 청크/STT와 final 전사 수집, Jev 판단·RAG/LLM/NONE의 실제 도구 이력.
4. Discord 연결/수집/허용 채널/원문 수정·삭제와 맥락별 할 일 도출.
5. mini snapshot/SSE와 재접속·다중 작업·실패 표시, 프론트 매핑.

API 제안과 별도의 [ERD 변경 전달안](ERD-PROPOSAL-2026-10-12.md), [DBML 확장 도식](erd-context-assistant.dbml)을 함께 전달한다. ORM 모델·마이그레이션·프론트 구현을 이번 문서 작업에서 바꾸지는 않았다.
