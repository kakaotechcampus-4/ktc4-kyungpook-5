# API Reference

이 문서는 전체 API의 지도다. 도메인별로 어떤 엔드포인트가 있고 권한이 무엇인지 한눈에 보기 위한 것이지, 정확한 요청·응답 스키마 문서가 아니다. 필드 단위 구조(타입, 필수 여부, enum 값 등)는 서버 기동 후 `/docs`(Swagger)에서 코드로부터 자동 생성된 스펙을 확인한다. 기능별 설계 배경은 `docs/*.md`(`event-operations.md`, `meeting-audio.md`, `meeting-beta.md`, `operations-verification.md`, `record-search.md`)에 따로 있다.

## 공통 규칙

- **응답 봉투**: 성공 응답은 모두 `{"data": ..., "meta": ...}` 형태(`Envelope[T]`, `app/schemas/common.py`). 단건 응답은 `meta`가 없고, 목록 응답은 `meta`에 `page`, `size`, `totalCount`가 담긴다(`PageMeta`).
- **에러 형식**: 실패 응답은 `{"error": {"code": ..., "message": ..., "fields": ...}}` 하나로 통일한다(`app/core/exceptions.py`). `fields`는 입력 검증 실패일 때만 붙는다. FastAPI 기본 `{"detail": ...}` 핸들러는 쓰지 않는다.
- **대소문자**: API 경계는 전부 camelCase다(`CamelModel`, `alias_generator=to_camel`). 내부 코드(모델·서비스)는 snake_case를 쓰고 스키마 레이어가 변환한다.
- **인증**: 표준 OAuth2/HTTPBearer 스킴이 아니라 **커스텀 Header 의존성**이다(`app/core/deps.py`의 `get_current_account`). `Authorization: Bearer <access-token>` 헤더를 직접 파싱하며, access token은 매 요청마다 `auth` 테이블(DB)로 검증한다(JWT 자체 검증이 아님 — 로그아웃·정지 시 즉시 차단하기 위해서, #131). 이 때문에 Swagger UI의 자물쇠 아이콘("Authorize") 버튼이 동작하지 않는다 — 각 엔드포인트의 `authorization` 파라미터 입력란에 `Bearer <token>`을 직접 타이핑해야 한다.
- **권한 단계**: 아래 표의 권한 열은 이 앱의 실제 역할 체계를 그대로 쓴다.
  - `비로그인`: 인증 불필요.
  - `로그인`: `get_current_account`만 거친다. 로그인한 계정이면 되고, 특정 동아리 소속 여부는 별도로 확인(또는 불필요).
  - `회장·임원`: `require_member` / `ensure_member` / `require_club_role(OWNER, MANAGER)`를 거친다. 이 서비스에서 "동아리 멤버"로 취급하는 대상은 사실상 **회장(OWNER)·임원(MANAGER)뿐**이다 — `MemberRole.MEMBER`는 기존 명단 호환용으로만 남아 있고 `SERVICE_ROLES = (OWNER, MANAGER)`가 실질적인 "멤버" 기준이다(`app/core/enums.py`). 즉 표에서 "회장·임원"이라고 적은 건 일반적 의미의 "멤버 아무나"에 대응한다.
  - `OWNER`: `require_club_role(MemberRole.OWNER)`. 회장만 가능한 좁은 권한(동아리 정보 수정 등).
  - `서비스 계정`: `require_service_account`. club_id가 경로에 없는 전역 기능(Push)에서, 최소 한 동아리의 회장·임원인 계정만 허용.
- **낙관적 동시성 제어(Optimistic concurrency)**: 많은 수정·상태전이 엔드포인트가 요청 본문에 `expectedVersion`(또는 `expectedRevision`류)을 요구한다. 서버의 현재 버전과 다르면 409 `VERSION_CONFLICT`류 에러를 반환한다. 표의 "비고"에 `expectedVersion`으로 표시했다.
- **비동기 작업(202 + 폴링)**: 바로 끝나지 않는 작업(영수 가져오기, Discord 동기화 등)은 202를 반환하고 `AgentJob`을 만든다. 진행 상태는 `GET /api/v1/agent-jobs/{job_id}`로 폴링한다.
- **SSE 스트리밍**: 일부 엔드포인트는 Server-Sent Events로 응답한다(`text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`, 15초 간격 heartbeat 주석). 표에 `SSE`로 표시했다.
- **Idempotency-Key**: AI를 호출하는 일부 POST(행사 계획 chat/generate류)는 `Idempotency-Key` 헤더를 받는다. 연결이 끊겨도 같은 키로 결과를 다시 조회할 수 있는 별도 GET이 있어, 재시도 때 AI를 다시 호출하지 않는다.
- **WebSocket**: `GET /api/v1/meetings/{meeting_id}/stream`은 WebSocket이며, 브라우저가 커스텀 헤더를 못 보내 쿼리 파라미터 `token`으로 인증한다(자세한 프로토콜은 `docs/meeting-audio.md`).

---

## 1. 인증 (`auth.py`)

로그인·회원가입·토큰 발급. 전부 `/api/v1/auth` 하위.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| POST | `/auth/signup` | 이메일·비밀번호로 회원가입 | 비로그인 |
| POST | `/auth/email/verify` | 이메일 인증 토큰 확인 | 비로그인 |
| POST | `/auth/login` | 이메일·비밀번호 로그인, access/refresh 토큰 발급 | 비로그인 |
| POST | `/auth/kakao/callback` | 카카오 인가 코드를 교환해 로그인 | 비로그인 |
| POST | `/auth/refresh` | refresh token으로 access token 재발급 | 비로그인 |
| POST | `/auth/logout` | refresh token 폐기(204) | 로그인 |

---

## 2. 동아리·멤버십 (`clubs.py`)

동아리 생성·조회·초대·멤버 목록. `/api/v1` 하위.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| GET | `/me` | 내 계정 정보 + 소속 동아리 목록 | 로그인 |
| GET | `/clubs?query=` | 동아리 이름 검색(회원가입 중에도 호출) | 비로그인 |
| POST | `/clubs` | 동아리 생성(생성자가 OWNER가 됨) | 로그인 |
| GET | `/clubs/{club_id}` | 동아리 상세 | 회장·임원 |
| PATCH | `/clubs/{club_id}` | 동아리 이름·분야·소개 수정 | OWNER |
| POST | `/clubs/{club_id}/invitations` | 가입 초대 생성(토큰은 응답에만 노출, DB엔 해시만 저장) | 회장·임원 |
| POST | `/invitations/accept` | 초대 토큰으로 가입 | 로그인 |
| GET | `/clubs/{club_id}/members` | 멤버 목록 | 회장·임원 |

---

## 3. 행사 — 조회·상태 전이 (`events.py`)

행사 생성과 `PLANNING → ON_GOING → COMPLETE` 생명주기, 취소 플로우. `/api/v1/events` 하위. 계획(P1/P2) 관련 엔드포인트는 4번 섹션에 별도로 정리했다(같은 라우터 파일).

> **라우트 순서 주의**: `GET /events/drafts`는 코드상 `GET /events/{event_id}`보다 먼저 등록돼 있다. 순서가 바뀌면 "drafts"가 `event_id`로 잘못 매칭된다.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/events` | 행사 목록(`clubId` 필수 쿼리, `status` 선택) | 회장·임원 | 페이지네이션 |
| GET | `/events/drafts` | 초안(미확정) 행사 목록 | 회장·임원 | `/{event_id}`보다 먼저 등록 |
| POST | `/events` | 행사 생성(제목만, 내용은 계획 대화로 채움) | 회장·임원 | |
| GET | `/events/{event_id}` | 행사 상세 | 회장·임원 | |
| POST | `/events/{event_id}/start` | PLANNING → ON_GOING | 회장·임원 | |
| POST | `/events/{event_id}/complete` | ON_GOING → COMPLETE | 회장·임원 | |
| POST | `/events/{event_id}/cancel` | 취소 절차 시작 | 회장·임원 | |
| GET | `/events/{event_id}/cancel/tasks` | 취소 체크리스트 + 상태(DONE/CURRENT/TODO) | 회장·임원 | |
| POST | `/events/{event_id}/cancel/tasks/{task_id}/complete` | 취소 체크리스트 항목 하나 완료 | 회장·임원 | |

---

## 4. 행사 계획 P1·P2 (`events.py`, plan 하위 경로)

AI와의 계획 대화, 단계(Step) 구성, 계획 검토. `PLANNING` 상태인 행사에서만 변경계가 동작한다(`_ensure_planning()`).

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/events/{event_id}/plan/chat` | 계획 대화 한 턴 | 회장·임원 | Idempotency-Key, `base_revision`; AI 호출 전 세션 close(트랜잭션 점유 방지) |
| POST | `/events/{event_id}/plan/chat/stream` | 위와 동일, SSE로 스트리밍 | 회장·임원 | SSE, Idempotency-Key |
| GET | `/events/{event_id}/plan/requests/{request_key}` | Idempotency-Key로 제출했던 요청의 결과 재조회(연결 끊김 복구용) | 회장·임원 | |
| GET | `/events/{event_id}/plan/messages` | 계획 대화 메시지 목록 | 회장·임원 | |
| GET | `/events/{event_id}/plan/steps` | 계획된 단계 + 각 단계의 Action 목록 | 회장·임원 | |
| GET | `/events/{event_id}/plan/steps/snapshot` | 단계 스냅샷 + `base_revision`/`plan_revision`(신선도 비교용) | 회장·임원 | 읽는 동안 Event 행 잠금(모든 계획 writer 공유) |
| PATCH | `/events/{event_id}/plan/steps` | 포함할 단계 집합·순서 교체 | 회장·임원 | `expected_revision` |
| POST | `/events/{event_id}/plan/generate` | AI 계획 초안 생성 | 회장·임원 | Idempotency-Key, 세션 close 패턴 |
| POST | `/events/{event_id}/plan/generate/stream` | 위와 동일, SSE | 회장·임원 | SSE, Idempotency-Key |
| GET | `/events/{event_id}/plan` | 계획 화면 전체 뷰 | 회장·임원 | |
| POST | `/events/{event_id}/plan/review` | 계획 수정안에 대한 AI 검토(#177) | 회장·임원 | `expected_revision`; AI 실패는 200 + `status: FAILED`로 반환(에러 아님) |
| GET | `/events/{event_id}/actions` | 행사의 Action 목록 | 회장·임원 | `status`(콤마 구분 다중값), `type`, `excludeType` 필터, 페이지네이션 |
| GET | `/events/{event_id}/steps` | 행사의 단계 목록(Action 중첩 없음) | 회장·임원 | |

---

## 5. 단계·행동(Step/Action) 처리 (`actions.py`, `steps.py`, `plan_items.py`)

운영 중(`ON_GOING`) 행사에서 Action을 승인·거절·완료 처리하고, 계획 단계/행동의 세부 필드를 직접 수정한다.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/actions/{action_id}/approve` | Action 승인 | 로그인(+행사 소속 확인) | `expectedVersion`; 행사가 운영 중이어야 함 |
| POST | `/api/v1/actions/{action_id}/deny` | Action 거절(사유 포함) | 로그인(+행사 소속 확인) | `expectedVersion` |
| POST | `/api/v1/actions/{action_id}/resolve` | 확인 요청에 대한 선택 응답(선택지 또는 수동 입력) | 로그인(+행사 소속 확인) | `expectedVersion` |
| POST | `/api/v1/actions/{action_id}/done` | 운영진이 직접 실행 완료로 표시(앱이 발송·이체를 대신하지 않음) | 로그인(+행사 소속 확인) | `expectedVersion` |
| POST | `/api/v1/actions/{action_id}/draft` | 토리 본문 초안 재생성 요청(#334) — 즉시 DRAFTING 반환, FE가 `contentStatus` 폴링 | 로그인(+행사 소속 확인) | `expectedVersion` |
| POST | `/api/v1/steps/{step_id}/complete` | MANUAL 단계 등 사람이 직접 완료 처리(행동이 모두 끝난 단계는 서버가 자동 완료) | 로그인(+행사 소속 확인) | 행사가 운영 중이어야 함 |
| PATCH | `/api/v1/steps/{step_id}` | 단계 필드(시작·마감) 직접 수정 | 회장·임원 | `expectedVersion` |
| PATCH | `/api/v1/actions/{action_id}` | Action 필드(제목·금액·내용 등) 직접 수정, 보낸 키만 덮어씀 | 회장·임원 | `expectedVersion` |

---

## 6. 영수 내역·회계 (`accounting.py`)

지출 기록과 영수증 이미지/내역 가져오기. `/api/v1/clubs/{club_id}` 하위.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/expenses` | 지출 직접 등록 | 회장·임원 | |
| GET | `/expenses` | 지출 목록 | 회장·임원 | 페이지네이션 |
| GET | `/expenses/{expense_id}` | 지출 상세 | 회장·임원 | |
| PATCH | `/expenses/{expense_id}` | 지출 수정 | 회장·임원 | `expectedVersion` |
| DELETE | `/expenses/{expense_id}` | 지출 삭제(204) | 회장·임원 | |
| POST | `/receipt-imports` | 영수증 이미지/파일 업로드 → 가져오기 작업 시작 | 회장·임원 | 202, multipart(`type` + `file`), 비동기 job |
| POST | `/receipt-imports/{import_id}/retry` | 실패한 가져오기 재시도 | 회장·임원 | |
| GET | `/receipt-imports` | 가져오기 목록(요약 형태만) | 회장·임원 | 페이지네이션 |
| GET | `/receipt-imports/{import_id}` | 가져오기 상세(행별 데이터·오류 포함) | 회장·임원 | |
| PATCH | `/receipt-imports/{import_id}/draft` | 가져온 행 초안 수정 | 회장·임원 | `expectedVersion` |
| POST | `/receipt-imports/{import_id}/confirm` | 확정 → Expense 레코드 생성(행사 연결 선택 가능) | 회장·임원 | `expectedVersion` |

---

## 7. 자료함 (`records.py`)

파일 업로드·목록·통합 검색. 자세한 검색 로직은 `docs/record-search.md` 참고. `/api/v1/records` 하위.

> **라우트 순서 주의**: `GET /category-counts`는 `GET /{record_id}`보다 먼저 등록해, "category-counts"가 자료 id로 잡히지 않게 한다.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/records/search` | 파일명·본문·의미 검색 통합 결과 | 로그인(+소속 확인) | `clubId`, `query` 필수, 페이지네이션 |
| GET | `/records/category-counts` | 카테고리별 자료 수 | 로그인(+소속 확인) | |
| GET | `/records` | 자료 목록 | 로그인(+소속 확인) | `category` 필터, 페이지네이션 |
| POST | `/records/{record_id}/index` | 색인 재시도 | 로그인(+소속 확인) | |
| POST | `/records` | 파일 업로드 | 로그인(+소속 확인) | multipart |
| GET | `/records/{record_id}` | 자료 상세 | 로그인(+소속 확인) | |
| GET | `/records/{record_id}/file` | 원본 파일 다운로드 | 로그인(+소속 확인) | |
| DELETE | `/records/{record_id}` | 자료 삭제(204) | 로그인(+소속 확인) | |

---

## 8. 회의 (`meetings.py`)

회의 생성, 실시간 음성 스트림(WebSocket), 전사, 회의 후 검토(화자 분리·할 일 후보 추출). 자세한 프로토콜은 `docs/meeting-audio.md`, `docs/meeting-beta.md` 참고. 기존 HTTP 청크 업로드는 TEST_MODE 전용 더미 경로다.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/clubs/{club_id}/meetings` | 회의 생성 | 회장·임원 | |
| GET | `/api/v1/clubs/{club_id}/meetings` | 회의 목록 | 회장·임원 | `status` 필터, 페이지네이션 |
| GET | `/api/v1/meetings/{meeting_id}` | 회의 상세 | 로그인(+소속 확인) | club_id가 경로에 없어 리소스 조회 후 멤버십 확인 |
| WS | `/api/v1/meetings/{meeting_id}/stream` | 실시간 PCM 음성 스트림(인증 subscriber + 단일 producer) | 쿼리 파라미터 `token` | 브라우저 WS 제약으로 헤더 대신 쿼리 인증 |
| POST | `/api/v1/meetings/{meeting_id}/audio-chunks` | (TEST_MODE 전용) HTTP 청크 업로드 | 로그인(+소속 확인) | 202, TEST_MODE 아니면 미구현 에러 |
| GET | `/api/v1/meetings/{meeting_id}/audio-chunks/{seq}/file` | 청크 원본 오디오 파일 | 로그인(+소속 확인) | |
| GET | `/api/v1/meetings/{meeting_id}/audio-chunks/{seq}/clip` | 청크 내 구간 클립(WAV) | 로그인(+소속 확인) | `startMs`/`endMs` |
| GET | `/api/v1/meetings/{meeting_id}/review/segments/{segment_id}/clip` | 전사 구간에 대응하는 오디오 클립 | 로그인(+소속 확인) | |
| GET | `/api/v1/meetings/{meeting_id}/transcripts` | 확정 전사 목록 | 로그인(+소속 확인) | `afterSeq` |
| POST | `/api/v1/meetings/{meeting_id}/finish` | 회의 종료 | 로그인(+소속 확인) | 202 |
| POST | `/api/v1/meetings/{meeting_id}/review` | 회의 후 검토 시작 | 로그인(+소속 확인) | 202 |
| GET | `/api/v1/meetings/{meeting_id}/review` | 검토 상태 조회 | 로그인(+소속 확인) | |
| PATCH | `/api/v1/meetings/{meeting_id}/review/speakers` | 화자 이름 매핑 수정 | 로그인(+소속 확인) | `expectedVersion` |
| POST | `/api/v1/meetings/{meeting_id}/review/draft` | 검토 초안(요약 등) 생성 | 로그인(+소속 확인) | `expectedVersion` |
| POST | `/api/v1/meetings/{meeting_id}/review/submit` | 화자 분리(diarization) 제출 | 로그인(+소속 확인) | 202; 제공자 응답 불확실(`SUBMISSION_UNKNOWN`) 시 중복 과금 방지를 위해 재제출하지 않음, 재시도는 FAILED 상태에서만 |
| POST | `/api/v1/meetings/{meeting_id}/review/poll` | 화자 분리 진행 상태 폴링 | 로그인(+소속 확인) | |
| POST | `/api/v1/meetings/{meeting_id}/review/candidates` | 검토 결과로 할 일 후보 저장 | 로그인(+소속 확인) | 201 |

---

## 9. Discord (`discord.py`)

Discord 연결 설정과 메시지 읽기. **읽기 전용** — Discord에 글을 쓰는 경로는 없다. `/api/v1` 하위.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/clubs/{club_id}/discord-connections` | 연결 생성 | 회장·임원 | 201 |
| GET | `/discord-connections/{connection_id}` | 연결 상세 | 로그인(+소속 확인) | |
| PATCH | `/discord-connections/{connection_id}` | 연결 수정(활성화 여부, 채널) | 로그인(+소속 확인, 회장·임원만) | `expectedVersion` |
| POST | `/discord-connections/{connection_id}/sync` | 메시지 동기화 시작 | 로그인(+소속 확인, 회장·임원만) | 202, AgentJob |
| GET | `/discord-connections/{connection_id}/messages` | 동기화된 메시지 목록 | 로그인(+소속 확인) | `limit` |

---

## 10. 할 일 후보·확정 항목·리마인더 (`tasks.py`, `confirmed_tasks.py`, `reminder_recipients.py`)

회의/Discord 등에서 추출된 할 일 후보를 검토·수락하고, 명시적 확인 후 확정 항목으로 저장·관리한다.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/clubs/{club_id}/task-suggestions` | 할 일 후보 목록 | 회장·임원 | `sourceType`, `status`, `meetingId` 필터 |
| GET | `/api/v1/clubs/{club_id}/task-suggestions/{suggestion_id}` | 후보 상세 | 회장·임원 | |
| PATCH | `/api/v1/clubs/{club_id}/task-suggestions/{suggestion_id}` | 후보 내용 수정 | 회장·임원 | |
| POST | `/api/v1/clubs/{club_id}/task-suggestions/{suggestion_id}/accept` | 후보 수락 | 회장·임원 | `expectedVersion` |
| POST | `/api/v1/clubs/{club_id}/task-suggestions/{suggestion_id}/confirm` | 사용자 확인 후 확정 항목으로 저장·예약 | 회장·임원 | |
| GET | `/api/v1/clubs/{club_id}/confirmed-tasks` | 확정 항목 목록 | 회장·임원 | `suggestionId`, `meetingId` 필터 |
| GET | `/api/v1/clubs/{club_id}/confirmed-tasks/{item_id}` | 확정 항목 상세 | 회장·임원 | |
| PATCH | `/api/v1/clubs/{club_id}/confirmed-tasks/{item_id}` | 확정 항목 수정 | 회장·임원 | |
| POST | `/api/v1/clubs/{club_id}/confirmed-tasks/{item_id}/cancel` | 확정 항목 취소 | 회장·임원 | `expectedVersion` |
| GET | `/api/v1/clubs/{club_id}/reminder-recipients` | 알림 수신자 최소 명단(이메일·전화 등 비노출) | 회장·임원 | |

---

## 11. Push (`push.py`)

브라우저 Push 구독 관리. club_id가 경로에 없는 전역 기능이라 "서비스 계정"(최소 한 동아리의 회장·임원) 권한을 쓴다. opaque Bearer로 로그인한 자신의 기기 구독만 다룬다. `/api/v1/push` 하위.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/vapid-public-key` | VAPID 공개키 조회 | 서비스 계정 | |
| GET | `/subscriptions` | 내 구독 목록 | 서비스 계정 | |
| POST | `/subscriptions` | 구독 등록 | 서비스 계정 | 201 |
| DELETE | `/subscriptions/{subscription_id}` | 구독 해제 | 서비스 계정 | |
| POST | `/test` | 테스트 푸시 발송 | 서비스 계정 | 응답은 서비스 접수 확인일 뿐, 실제 기기 표시는 별도 확인 필요 |

---

## 12. 작업(agent-jobs)·판단 기록·mini 활동 (`agent.py`)

비동기 작업 폴링, AI 판단 기록 조회, 동아리 mini 활동 피드(SSE). `/api/v1` 하위.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/agent-jobs/{job_id}` | 비동기 작업 상태 폴링(영수 가져오기, Discord 동기화 등 공용) | 로그인(+소속 확인) | |
| GET | `/clubs/{club_id}/context-decisions` | AI 판단 기록 목록 | 회장·임원 | `sourceType`, `meetingId`, `connectionId` 필터 |
| GET | `/clubs/{club_id}/context-decisions/{decision_id}` | 판단 기록 상세 | 회장·임원 | |
| GET | `/clubs/{club_id}/activity` | mini 활동 스냅샷(커서, 캐릭터 상태, 진행 중 작업, 연결, 대기 중 제안 수) | 회장·임원 | |
| GET | `/clubs/{club_id}/activity/stream` | 위 스냅샷을 실시간으로 미는 SSE | 회장·임원 | SSE, `Last-Event-ID`로 재개, 1초 폴링 간격, 15초 heartbeat. 스트림 수명 내내 DB 세션을 붙잡지 않으려 매 폴링마다 짧은 세션을 새로 연다 |

---

## 13. 토리 대화 (`tori.py`)

동아리 전용 챗봇. 의도(자료 검색/할 일 조회/행사 목록/이동 안내 등)를 분류해 응답한다. `/api/v1/clubs/{club_id}/tori` 하위.

| 메서드 | 경로 | 설명 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| POST | `/messages` | 토리에게 메시지 전송, 의도별 응답(자료 검색·할 일 목록·행사 목록·화면 이동·자기소개 등) | 회장·임원 | AI 호출 전 커밋(DB 커넥션 점유 방지); 모호한 명확화 답변은 임의로 연도·행사를 좁히지 않음 |

---

## 14. 행사 운영 상황 (`operation_cases.py`)

진행 중 행사에서 "지금 어떤 상황인지" AI에게 물어보고 기록하는 기능. `/api/v1/events/{event_id}/operation-cases` 하위. 자세한 내용은 `docs/operations-verification.md` 참고.

| 메서드 | 경로 | 설명 | 인증 |
| --- | --- | --- | --- |
| POST | `/` | 운영 상황 케이스 생성 | 로그인(+행사 소속 확인) |
| GET | `/` | 케이스 목록 | 로그인(+행사 소속 확인) |
| GET | `/{case_id}` | 케이스 상세 | 로그인(+행사 소속 확인) |
| POST | `/{case_id}/question` | 케이스에 대한 추가 질문 실행 | 로그인(+행사 소속 확인) |
| POST | `/{case_id}/result` | 케이스 결과 실행 | 로그인(+행사 소속 확인) |

---

## 테스트 전용 (`test_support.py`)

`TEST_MODE=true`일 때만 등록되는 라우터(`/api/v1/test-support`)로, 운영 환경에는 아예 올라가지 않는다(404가 아니라 라우트 자체가 없음). 브라우저 동의 화면처럼 curl/자동화로 재현할 수 없는 경로(카카오 로그인 우회, Discord 이벤트 주입, 전사 주입 등)를 대신한다. 실제 서비스 동작과 무관하므로 이 문서의 메인 레퍼런스에서는 제외한다.
