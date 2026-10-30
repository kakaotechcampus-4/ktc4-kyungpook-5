# 운영해 · BE

인증·동아리·영수 내역·회의·기록·할 일 후보·확정 항목·예약·Push 구독은 실제 DB로 동작합니다.
자료는 실제 `index_record`와 pgvector 저장소, 음성은 WS PCM→BE VAD→Whisper 어댑터로 연결합니다.
회의 판단은 최신 AI의 `judge_utterance(request, records=...)`와 결합해야 합니다.
독립 후보 추출 계약과 실제 공급자 설정이 없으면 해당 기능의 실패를 명시합니다.
실행·API·상태·검증 범위는 [회의 베타 연결](docs/meeting-beta.md)과 [WS 계약](docs/meeting-audio.md)을 보세요.
기존 test-support/HTTP STT·Discord 처리의 개발 fixture와 OCR 더미는 실연동이 아닙니다.
행사(`/events`) 조회·계획 확정·행동 처리와 P1·P2 계획 API도 실제 DB로 동작합니다 (#41, #187). 단계 수정·재배열은 아직 없습니다.
모델 확정 내역과 그 근거는 [BE 스키마 검토안](../docs/week6/be/운영해_BE_스키마_검토안.md)에 있습니다.

서비스 사용자는 동아리 **회장·대표(`OWNER`)와 임원(`MANAGER`)**입니다.
별도 `ADMIN` 역할은 없으며, 일반 동아리원은 서비스 이용 대상이 아닙니다.
기존 `MEMBER` 명단 행은 보존하지만 소속 API·WS 접근/초대/알림 대상에서 제외합니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 언어 | Python 3.12 | AI와 통일 |
| API 프레임워크 | FastAPI | FE가 호출하는 API 서버 |
| DB | PostgreSQL | 금액은 정수 원 단위로만 저장 (NF2) |
| ORM | SQLAlchemy 2.0 | 비동기 세션(`AsyncSession`) + psycopg 3. AI 호출이 async라 DB도 async로 맞춤 (#52, #63) |
| 마이그레이션 | Alembic | `alembic/`. 초기 스키마 리비전과 현재 사용자 시드 리비전이 있습니다 (#63) |
| 파일 저장 | AWS S3 (`infra/s3.py`) | 영수증·기록 원본 업로드 |
| 기록 파일 파싱 | pypdf · openpyxl | PDF·XLSX를 `parse_result`로 변환 (`services/record_parser.py`). CSV는 표준 `csv` |
| 패키지 관리 | uv | AI와 동일하게 `pyproject.toml` 기반 |
| 인증 | DB 세션·opaque Bearer | 기존 로그인/소속/역할 검증 유지 |
| 배포 환경 | AWS EC2 + Docker Compose | RDS 병행 여부 미정 |
| 테스트 | pytest | `tests/unit`은 `event_rules.py` 순수 함수, `tests/integration`은 라우터 엔드투엔드 |
| 린트 · 포맷 | 미정 | 첫 구현에서 도구와 실행 명령 결정 |

### 확인이 필요한 항목

- FE 명세 반영이 필요한 5건 — [검토안 §4](../docs/week6/be/운영해_BE_스키마_검토안.md)
- 회의·확인이 필요한 항목 — [검토안 §5](../docs/week6/be/운영해_BE_스키마_검토안.md)
- `transactions`(개별 입금 내역) 테이블 — 금액 안건 확정 후 추가. `participants`(행사별 참가 신청)는 #107로 추가됨
- `app.ai`의 독립 후보 추출 계약과 실제 공급자 설정 — 회의 판단은 공개 `judge_utterance(request, records=...)`를 사용하며 BE↔AI는 HTTP가 아닌 함수 호출
- S3 버킷 구조와 접근 권한 — 영수증 등 민감 파일이 포함되어 NF6(민감정보 최소 수집)과 연결됨

RAG 임베딩 저장 위치는 PostgreSQL pgvector(`vector(1536)`)로 확정

## 반드시 지켜야 할 규칙

1. 금액·정원·매칭·환불 판정 같은 결정론적 계산은 `services/event_rules.py`의 순수 함수로 구현한다. 라우터와 AI 서비스는 이 결과를 그대로 받아 쓸 뿐, 계산을 직접 하거나 보정하지 않는다 (NF1).
2. 외부에 영향을 주는 실행은 사용자 확인을 거친다 (NF3). 회의 예약 알림은 OWNER/MANAGER의 명시적 confirm으로 확정 항목/담당/수신자/시각을 저장한 뒤 실행한다. 기존 행사 공지·송금·환불의 승인 계약을 이 확인으로 대체하지 않는다.
3. Agent 호출 이력과 승인 이력은 빠짐없이 기록하고 수정·삭제하지 않는다. 상태가 바뀌면 새 레코드를 추가해 이전 상태를 덮어쓰지 않는다 (NF4).
4. 라우터는 `services/`를 거쳐서만 모델과 계산을 조합한다. 다른 도메인의 `event_rules.py`나 `models/`를 직접 끌어와 우회하지 않는다.

## 폴더 구조

```text
be/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py           # BE 설정. AI_* 는 app/ai/config.py의 AISettings를 재사용
│   │   ├── security.py
│   │   ├── exceptions.py
│   │   ├── enums.py           # 도메인 enum (DB·API 모두 문자열 코드)
│   │   └── deps.py
│   ├── db/
│   │   ├── base.py            # Base · IdMixin · TimestampMixin · enum_column · JsonB
│   │   └── session.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── clubs.py
│   │   ├── events.py        # 계획, 참가자, 결제, 지출, 승인, 업무 전부 포함
│   │   ├── records.py       # 동아리 기록 업로드·조회
│   │   ├── accounting.py    # 지출 직접 입력·CSV·영수증 OCR 초안·확정
│   │   ├── meetings.py      # 회의·음성 청크·전사·WebSocket
│   │   ├── discord.py       # Discord 연결·수집 메시지 (읽기 전용)
│   │   ├── tasks.py         # 할 일 후보 조회·수정·수락
│   │   ├── agent.py         # 작업 상태·Jev 판단 조회·mini 활동 snapshot/SSE
│   │   └── test_support.py  # TEST_MODE 전용 주입 경로
│   ├── schemas/               # 라우터 파일마다 하나 (auth·clubs·events·records·accounting·meetings·discord·tasks·agent)
│   ├── models/
│   │   ├── __init__.py        # 전 모델 등록 (Base.metadata). 테이블 목록은 아래 "데이터 모델"
│   │   └── ...
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── club_service.py
│   │   ├── event_service.py   # 계획/참가자/승인/업무 오케스트레이션
│   │   ├── event_rules.py     # 참가비·환불·정산 계산 순수함수 (규칙 엔진, NF1)
│   │   ├── record_service.py
│   │   ├── record_parser.py   # 기록 원본(PDF·CSV·XLSX) → parse_result
│   │   ├── accounting_service.py · expense_csv_parser.py · receipt_ocr_stub.py
│   │   ├── meeting_service.py · meeting_stt_stub.py · meeting_judge_stub.py
│   │   ├── context_service.py      # Jev 판단 작업·판단 기록·할 일 후보 생성
│   │   ├── context_tools_stub.py   # 기록 검색·문장 생성·Discord 할 일 도출 더미
│   │   ├── agent_job_service.py    # 작업 상태 전이 + mini 활동 이벤트 기록
│   │   ├── activity_service.py     # mini snapshot·SSE 이벤트 조회
│   │   ├── discord_service.py · task_service.py
│   ├── infra/
│   │   ├── s3.py
│   │   └── storage.py         # 업로드 파일 저장 (S3 연동 전까지 로컬 디스크 STORAGE_DIR)
│   └── ai/                    # AI 모듈. 별도 서버 아님 — BE 프로세스 내부
│       ├── __init__.py        # BE가 쓰는 단일 공개 진입점 (회의 판단은 최신 AI 필요)
│       ├── facade.py          # BE → AI: 공개 기능 구현 위치
│       ├── ports.py           # AI → BE: BE가 주입하는 조회·계산 인터페이스
│       ├── contracts.py       # BE↔AI 공개 요청·응답 데이터 계약
│       ├── config.py          # AI_* 환경변수 (ML API 게이트웨이 설정)
│       ├── llm.py             # 채팅 모델 생성
│       ├── features/          # planning · retrieval · operations
│       ├── workflow/          # LangGraph 분기·연결
│       └── tools/             # Agent가 쓰는 도구 (accounting · events · records)
├── tests/
│   ├── unit/                  # event_rules.py 순수함수 테스트
│   └── integration/           # 라우터 엔드투엔드 테스트
├── alembic/
├── .env.example
└── pyproject.toml
```

레이어드 아키텍처로 역할을 나누고, 레이어 내부는 인증(`auth`)·동아리(`clubs`)·행사(`events`)·기록(`records`) 도메인별로 파일을 나눕니다.
`models/`에는 이 넷에 들어가지 않는 `agent.py`(AI 호출 로그)와 `chat.py`(계획 대화)를 더 둡니다. `events.py`에 함께 넣으면 한 파일에 테이블이 여섯 개가 되기 때문입니다.

| 레이어 | 역할 |
| --- | --- |
| `routers` | 요청을 받는 API 엔드포인트 |
| `schemas` | Pydantic 기반 요청·응답 데이터 형식 |
| `services` | 비즈니스 로직 구현 |
| `models` | DB 테이블과 매핑되는 ORM 모델 |
| `db` | DB 연결과 세션 관리 |
| `core` | 설정, 인증, 에러 처리 등 공통 모듈 |
| `infra` | S3 등 외부 연동. AI는 별도 연동이 아니라 `app/ai/` 내부 모듈 |

## 모듈별 담당 범위

| 모듈 | 담당 | 예시 |
| --- | --- | --- |
| `services/event_rules.py` | 참가비·환불·정산 등 결정론적 계산 (순수 함수, NF1) | 확정 인원 39명, 최소 인원 40명 → 미달 판정 |
| `routers/*` | FE가 호출하는 REST 엔드포인트, 요청 검증 | `POST /events/{id}/participants/{id}/cancel` (`routers/events.py`) |
| `services/event_service.py` | 계산 결과와 모델 변경을 하나의 트랜잭션으로 조합 (오케스트레이션) | 취소 처리 시 환불 판정 + 인원 재계산 + 후속 질문 생성을 함께 커밋 |
| `app/ai/facade.py` | BE → AI 공개 기능 호출 (HTTP 아님, 함수 호출) | 취소로 인한 영향 설명·대응안 생성을 AI에 요청 |
| `app/ai/ports.py` | AI → BE 조회·계산 인터페이스 (BE가 구현체 주입) | AI가 최소 인원 미달 판정 결과를 받아 대응안 생성 |
| `services/record_parser.py` | 기록 원본을 AI 색인 입력과 같은 `parse_result`로 변환 (순수 함수) | `2025 상반기 장부.xlsx`의 각 행 → `"날짜: 2025-03-03, 금액: 45000"` 블록 |
| `infra/s3.py` | 영수증·기록 원본 파일 업로드·조회 | 지출 등록 시 영수증 이미지를 S3에 올리고 URL을 `expense`에 저장 |

`services/event_rules.py`는 AI(`tools/accounting.py` 등)가 Tool로 호출하는 계산이기도 합니다. AI는 직접 계산하지 않고
`ports.py`로 주입된 이 결과를 그대로 받아 쓰며, 이 경계는 `contracts.py`의 데이터 계약으로도 명시합니다.
AI는 BE의 모델·DB·서비스를 직접 import하지 않습니다.

## 데이터가 흐르는 경로 (예: 참가자 취소)

```text
요청 → routers/events.py (취소 엔드포인트)
        → services/event_rules.py: 환불 규칙·기한 경계 판정, 최소 인원 재계산
        → services/event_service.py: 판정 결과 반영 + 후속 질문 레코드 생성 (하나의 트랜잭션)
        → app/ai/facade.py: 영향 설명·대응안 생성 필요 시 AI 기능 호출 (HTTP 아님)
   ← 환불 판정 + 영향 + 후속 질문을 함께 응답
```

실제 분기와 AI 호출 시점은 기능 구현 시 구체화합니다.

## API 연동

BE는 두 방향에서 호출됩니다. 실제로 HTTP를 타는 건 FE → BE 하나뿐이고, BE ↔ AI는 같은 프로세스 안의 함수 호출입니다.

- **FE → BE (HTTP)**: 행사 생성, 질문·답변, 대안 비교, 승인, 수납 대조, 취소·환불, 정산 조회 등 서비스의 주 REST API(`routers/clubs.py`, `routers/events.py`, `routers/records.py`).
- **BE → AI (함수 호출)**: BE는 `app.ai`에 재공개된 함수·DTO·port만 사용합니다. 별도 AI 서버·내부 HTTP 엔드포인트가 없습니다.
- **AI → BE (함수 호출)**: AI의 `tools/`가 계산·조회가 필요할 때 `app/ai/ports.py`에 정의된 인터페이스를 호출합니다. BE가 구현체를 주입하며 AI는 BE의 라우터·서비스·모델을 직접 import하지 않습니다.

함수명·입출력 필드 계약은 아직 미확정입니다. 공통 요청·응답 형식은 `app/schemas/`에서 라우터별로 관리하고, 에러 응답 형식(예: `MINIMUM_HEADCOUNT_VIOLATED`, `APPROVAL_REQUIRED`)은 `core/exceptions.py`를 통해 전 엔드포인트에서 동일한 구조를 씁니다.

## 데이터 모델

| 파일 | 테이블 |
| --- | --- |
| `models/clubs.py` | `clubs` · `members` · `invitations` |
| `models/auth.py` | `accounts` · `auth` |
| `models/common.py` | `idempotency_keys` |
| `models/events.py` | `events` · `steps` · `actions` · `participants` |
| `models/records.py` | `records` |
| `models/accounting.py` | `receipt_imports` · `receipt_import_rows` · `expenses` |
| `models/meetings.py` | `meetings` · `meeting_audio_chunks` · `transcript_segments` |
| `models/discord.py` | `discord_connections` · `discord_messages` |
| `models/agent.py` | `agent_log` · `agent_jobs` · `agent_activity_events` · `context_decisions` |
| `models/tasks.py` | `task_suggestions` |
| `models/chat.py` | `conversations` · `messages` |

팀장 요청 ERD 변경안(2026-10-12)에서는 curl 흐름에 필요한 것만 넣었습니다(`2ffdcc2aee5b` 리비전).
작업(`agent_jobs`)·판단(`context_decisions`)·할 일 후보(`task_suggestions`)를 나누고, 회의 판단 결과는
`transcript_segments`가 아니라 `context_decisions`에 둡니다. 판단 근거는 원문 id와 그때의 version을
`sources`(JSONB)에 고정하고, 전사가 정정되면 이전 판단을 `STALE`로 바꿉니다. 변경안의
`context_sources`/`context_source_versions`, `agent_job_attempts`, `agent_tool_calls`, `transcript_events`,
`discord_channels`, `task_suggestion_evidence`, `todos`는 아직 만들지 않았습니다(재시도·근거 버전 이력·
채널별 cursor가 필요해질 때 추가).

`participants`는 동아리 전체 명단(`members`)과 별개로 "이 행사에 신청했는지"를 행사별로 추적합니다
(이슈 #107). 미응답·응답 인원 집계가 이 테이블을 기준으로 계산됩니다.

공통 컬럼과 공유 컬럼 타입은 `db/base.py`에 있습니다. 모든 테이블이 `id`(접두어가 붙은 26자 문자열 PK)와
`created_at` · `modified_at`을 가집니다.

별도의 `Approval` 테이블은 두지 않습니다. 승인 대상은 `actions`이며 `status`와 `approve_needed`로
관리합니다. 다만 `status`를 덮어쓰는 현재 구조는 NF4와 어긋나므로, 승인 이력 테이블은 승인 정책이
확정된 뒤 별도로 추가합니다.

## 환경변수

| 이름 | 용도 | 상태 |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL 연결 문자열 (`postgresql+psycopg://...`) | 코드 반영됨 (`app/core/config.py`). 비어 있어도 앱은 뜨고 DB를 쓰는 시점에 실패 |
| `AI_API_BASE_URL` / `AI_API_KEY` / `AI_MODEL` | `app/ai/config.py` — ML API 게이트웨이 호출, 채팅 모델(`gpt-5.6-luna`) | 코드 반영됨 (`app/ai/config.py`) |
| `AI_REQUEST_TIMEOUT_SECONDS` | 단일 요청 응답 대기 상한(초). 비우면 60 | 코드 반영됨 (`app/ai/config.py`) |
| `AI_EMBEDDING_BASE_URL` / `AI_EMBEDDING_API_KEY` / `AI_EMBEDDING_MODEL` | 임베딩 전용 설정. 키를 비우면 `AI_API_KEY` 재사용 | 코드 반영됨 (`app/ai/config.py`) |
| `JWT_SECRET_KEY` / `SESSION_SECRET` | 인증 방식 확정 후 결정 | 미정 |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `infra/s3.py`의 S3 접근 인증 | 미정 |
| `S3_BUCKET_NAME` | 영수증·기록 파일을 저장할 버킷 | 미정 |

`.env.example`에는 값의 예시만 기록하고, 실제 값이 든 `.env`는 커밋하지 않습니다.

## 개발 환경 설치

저장소 루트에서 실행합니다. uv가 필요하며 Python은 3.12 계열을 사용합니다.

```bash
cd be
uv sync --locked
cp -n .env.example .env
```

`.env`의 DB 연결 정보, `AI_*` ML API 게이트웨이 설정, S3 접근 정보를 로컬 환경에 맞게 설정하세요. 기존 `.env`는 덮어쓰지 않습니다.

저장소 루트의 `compose.yml`로 `docker compose up` 한 번이면 FE(Vite)·BE(FastAPI)·PostgreSQL을 함께 띄울 수 있습니다 (이슈 #35, #63).
PostgreSQL만 따로 띄우려면 `docker compose up -d db`를 실행합니다. `localhost:5432`에 개발 DB `unyounghae`와 테스트 DB `unyounghae_test`가 만들어집니다(계정 `unyounghae`/`unyounghae`).

- 테스트 DB는 볼륨이 비어 있을 때만 만들어집니다. 없으면 `docker compose down -v`로 볼륨을 지운 뒤 다시 띄웁니다(로컬 DB 데이터도 지워집니다).
- 호스트에 PostgreSQL이 이미 5432 포트를 쓰고 있으면 포트가 겹칩니다.
- `alembic` 의존성이 추가됐으므로 기존 api 이미지는 `docker compose up --build`로 다시 빌드합니다.

## 마이그레이션

```bash
# compose 로 띄운 경우
docker compose exec api uv run --no-sync alembic upgrade head

# 호스트에서 실행하는 경우 (be/ 에서). be/.env 의 DATABASE_URL 을 읽는다
uv run alembic upgrade head
```

모델을 바꾸면 `uv run alembic revision --autogenerate -m "<설명>"`으로 리비전을 만들고 생성된 파일을 직접 검토합니다.
리비전을 만들지 않고 모델만 바꾸면 테스트(`alembic check`)가 실패합니다.

## 서버 실행

```bash
cd be
uv run uvicorn app.main:app --reload
```

`http://localhost:8000/docs` 에서 스키마와 요청을 확인할 수 있습니다.
CORS는 Vite 개발 서버(`http://localhost:5173`)만 허용합니다.

## 테스트

```bash
cd be
uv run pytest
```

서버를 띄우지 않고 `TestClient`로 앱을 직접 호출합니다.
`db` 마커가 붙은 테스트(세션 연결, 마이그레이션 왕복·`alembic check`, 시드)는 테스트 DB가 필요합니다.
기본 주소(`localhost:5432/unyounghae_test`)에 연결할 수 없으면 건너뛰므로, DB 없이도 나머지 테스트는 실행됩니다.
`TEST_DATABASE_URL`을 주면 그 주소를 쓰고, 이때는 연결에 실패하면 건너뛰지 않고 실패합니다. 빈 값도 준 것으로 보고 실패합니다.
`/test-support/*` 경로를 쓰는 테스트(카카오 로그인 우회, 회의 전사 주입 등)는 `TEST_MODE=true`도
**pytest를 띄우기 전에** 셸 환경변수로 줘야 합니다. `main.py`가 이 라우터를 앱 시작 시점에
한 번만 등록하므로, 테스트 안에서 `monkeypatch.setenv`로 주면 이미 늦습니다.

```bash
TEST_DATABASE_URL=... TEST_MODE=true uv run pytest
```
`tests/integration/`은 API의 응답 계약(`{data, meta}` 봉투, camelCase 키, enum 문자열,
에러 봉투)을 고정합니다. 공통 코드(`schemas`의 `CamelModel`, `core/exceptions.py`)를 바꿀 때
이 테스트가 먼저 깨지도록 두는 것이 목적입니다 (이슈 #33).

AI 모듈 테스트(`app/ai/tests/`)도 같은 명령으로 함께 실행됩니다.

## 팀장 요청 curl 흐름 (2026-10-12 서비스 계약)

`service-flow` → `accounting` → `meeting` → `discord` → `activity` curl 블록의 정상 흐름이 실제 DB로 끝까지 돕니다.
`service-errors`(권한·중복·수정·삭제·실패 주입) 블록은 이번 범위가 아닙니다.

```bash
cd be
uv run alembic upgrade head
TEST_MODE=true uv run python scripts/run_dev.py   # macOS/Linux는 TEST_MODE=true uv run uvicorn app.main:app
```

- `/test-support/*`(전사 주입, Discord FIXTURE 연결·이벤트 주입, 카카오 우회)는 `TEST_MODE=true`일 때만 등록됩니다.
- 이메일 인증·초대 토큰은 메일 대신 서버 콘솔에 찍힙니다(#131).
- curl이 쓰는 fixture는 `be/pm-tests/fixtures/`(`expense-valid.csv` 2행 32000원, `meeting-rules.csv` 회칙)에 있습니다.
  영수증 이미지·회의 음성 파일은 저장소에 없으니 아무 파일이나 지정하면 됩니다(내용을 읽지 않는 더미 처리).
- 업로드 파일은 `STORAGE_DIR`(기본 `./var/storage`)에 저장됩니다.

202로 접수하는 작업(OCR·STT·판단·Discord sync)은 실제 작업 큐가 없어 **요청 안에서 바로 처리**합니다. 응답을 받은
시점에 `GET /agent-jobs/{id}`는 이미 `SUCCEEDED`/`FAILED`입니다. 상태 전이(QUEUED → RUNNING(stage) → 완료)는
`agent_activity_events`에 남아 `GET /clubs/{id}/activity/stream`(SSE)으로 그대로 볼 수 있습니다.

| 더미 | 동작 |
| --- | --- |
| 영수증 OCR (`receipt_ocr_stub.py`) | 파일 해시로 금액을 정한 한 행 초안 |
| 회의 STT (`meeting_stt_stub.py`) | "(더미 전사) N번 음성 청크 …" 문장. 음성 내용은 읽지 않으므로 Jev 판단은 NONE |
| Jev 판단 (`meeting_judge_stub.py`) | 물음표 → RAG, "바꿔/써/정리해 주세요" 등 → LLM, 그 외 NONE |
| 기록 검색 (`context_tools_stub.py`) | 동아리 기록 `parse_result` 블록을 글자 2-gram 겹침으로 찾아 실제 `recordId`·위치를 인용 |
| 문장 생성 (`context_tools_stub.py`) | "(더미 생성) 요청 문장: …" |
| Discord 할 일 도출 (`context_tools_stub.py`) | 최근 메시지에 "~해야" 등이 있으면 LLM 분기로 보고 앞 메시지까지 근거로 후보 생성 |

curl 주석과 다르게 동작하는 부분입니다.

- `service-flow` 08 `POST /events`는 P1 행사 생성(#187)으로 생겼지만 curl 흐름에는 아직 반영하지 않아, 회의·지출의 `eventId`는 비워 둡니다.
- `meeting` M01 기록 업로드는 파싱 뒤 실제 색인을 시도합니다. 성공하면 `INDEXED`, 설정/모델 오류면 `COMPLETED`와 `indexError`를 반환합니다. 새 영구 검색은 `INDEXED`만 조회합니다. 기존 개발용 판단 fixture의 단순 검색은 실서비스 검색과 별개입니다.
- `meeting` M09 HTTP `finish`는 활성 WS가 없을 때 바로 종료합니다. 활성 WS에서는 409로 안내하므로 WS `end`→`audio.end_ack`(FINALIZING)→`audio.completed`를 기다립니다.
- `discord` D01 실제 연결은 `status=DISCONNECTED`입니다(curl 주석은 CONNECTED). 실제 bot 수집기가 없어 D02 `sync` 작업은 `FAILED`(`DISCORD_COLLECTOR_UNAVAILABLE`)로 남습니다. D03부터의 FIXTURE 연결은 `MONITORING`입니다.
- Discord 이벤트 주입은 `MESSAGE_CREATE`만 받습니다(수정·삭제는 오류 테스트 범위).
- `Idempotency-Key` 헤더는 받기만 하고 아직 적용하지 않습니다(`core/idempotency.py`는 #131에서 만들어 둠).
- mini `characterState`: 대기·처리 중 작업이 있으면 `WORKING`, 검토 안 한 할 일 후보가 있으면 `ATTENTION`, 아니면 `IDLE`. 실패 작업은 `jobs[]`에만 표시합니다.

## 행사 조회 API (#41)

모두 로그인이 필요하고, 그 행사가 속한 동아리의 대표·운영진만 볼 수 있습니다(일반 동아리원·다른 동아리는 403).
행사 데이터는 P1·P2 계획 생성(`POST /events/{id}/plan/generate`)으로 만들어집니다.

| 엔드포인트 | 화면 | 비고 |
| --- | --- | --- |
| `GET /api/v1/events?clubId=&status=&page=&size=` | M1·L1 카드 | `clubId` 필수. 시작일이 가까운 순, 날짜 없는 행사는 뒤 |
| `GET /api/v1/events/{eventId}` | L2 헤더 | `currentStep`을 id까지 내려 Step 모달을 바로 연다 |
| `GET /api/v1/events/{eventId}/steps` | L2 진행 상황·P2 묶음 | `phase`·`code` 포함. 거절·실패한 행동은 한 일·남은 일 어디에도 없음 |
| `GET /api/v1/events/{eventId}/actions` | M1 승인 대기·L2 | 아래 쿼리. 처리 안 된 것은 마감 임박 순, 처리된 것은 최근 처리 순 |

```bash
H="Authorization: Bearer <accessToken>"

# M1 승인 대기 (확인 요청 제외)
curl -H "$H" "localhost:8000/api/v1/events/<eventId>/actions?status=PENDING&excludeType=CONFIRMATION"

# L2 처리된 승인 최근 3건
curl -H "$H" "localhost:8000/api/v1/events/<eventId>/actions?status=APPROVED,DONE,DENIED&size=3"

# L2 확인 요청
curl -H "$H" "localhost:8000/api/v1/events/<eventId>/actions?type=CONFIRMATION"
```

계산 규칙은 `services/event_rules.py`에 있습니다.

- 단계 상태: 처음으로 `completed_at`이 비어 있는 단계가 `CURRENT`, 그 앞은 `DONE`, 뒤는 `TODO`.
- `dday`: KST 오늘 기준 시작일까지 남은 날 수. `pendingApprovalCount`는 `PENDING`이면서 확인 요청이 아닌 행동 수.
- `canApprove`: 요청자가 대표·운영진이고 행동이 `PENDING`일 때만 `true`. 승인 API도 같은 함수(`can_resolve`)로 검사한다.
- `editable`: `PENDING`·`APPROVED`일 때 `true` (#106 — 승인된 내용을 고치면 다시 `PENDING`).
- 확인 요청의 `options` / `allowManual`은 `actions.payload`(JSONB)에서 펼친다. `type=CONFIRMATION`인 건에만 값이 있다.
- `payment`·`budget`은 항상 `null`이다 (accounting 기준 재정의 예정, FE 연동 기준서 §5.1). `amount`는 계획 생성이 채우지 않아 지금은 비어 있다.

## 계획 확정·행동 처리·단계 완료 API (#41)

행사 상태에 따라 받는 요청이 나뉜다(#177 — 승인·실행 기록·단계 완료는 운영 시작 후의 일).

| 행사 상태 | 받는 요청 | 그 외 요청 |
| --- | --- | --- |
| `PLANNING` | 계획 대화·생성, `POST /api/v1/events/{eventId}:confirm` | 처리 API는 409 `EVENT_NOT_ON_GOING` |
| `ON_GOING` | 아래 처리 API | 계획 대화·생성·확정은 409 `EVENT_NOT_PLANNING` |

`:confirm`은 `PLANNING` → `ON_GOING`이며, 시작일이나 단계가 없으면 409 `PLAN_INCOMPLETE`(`fields`에 빠진 항목)다.
생성은 수십 초 걸려 그사이 확정될 수 있으므로, 생성 결과를 저장할 때도 `PLANNING`인지 다시 확인해 처리 기록을 덮어쓰지 않는다.

처리 API 요청·응답은 FE 명세 v1 §3을 따르고, 처리 요청에는 조회 응답의 `version`을 `expectedVersion`으로 보낸다
(`task-suggestions`와 같은 낙관적 잠금). 응답은 조회와 같은 `ActionOut`이다.

| 엔드포인트 | 하는 일 | 요청 |
| --- | --- | --- |
| `POST /api/v1/actions/{actionId}/approve` | `PENDING` → `APPROVED` | `{expectedVersion}` |
| `POST /api/v1/actions/{actionId}/deny` | `PENDING` → `DENIED`, 사유 저장 | `{expectedVersion, reason?}` (500자) |
| `POST /api/v1/actions/{actionId}/resolve` | 확인 요청 `PENDING` → `DONE`, 고른 답 저장 | `{expectedVersion, choice, manualValue?}` (`choice`는 선택지 key 또는 `MANUAL`) |
| `POST /api/v1/actions/{actionId}/done` | 운영진이 실행을 마쳤다는 기록. `APPROVED`(승인이 필요 없으면 `PENDING`) → `DONE` | `{expectedVersion}` |
| `POST /api/v1/steps/{stepId}/complete` | 단계를 직접 완료. 미처리 행동이 남아 있어도 된다 | 없음 |

- 이미 처리된 행동은 409 `ALREADY_RESOLVED`, 아직 대기 중인데 본 뒤에 내용이 바뀌었으면 409 `VERSION_CONFLICT`.
  둘 다 목록을 다시 불러오면 된다. 행을 잠그고 확인하므로 두 운영진이 동시에 눌러도 한 명만 처리된다.
- 확인 요청은 `/resolve`로만, 나머지는 `/approve`·`/deny`·`/done`으로만 처리한다(반대는 422).
  승인이 필요 없는 행동은 `/approve` 대상이 아니다(422).
- 조회의 `canApprove`는 위 조건(대표·운영진, `PENDING`, 운영 중, 확인 요청이거나 승인이 필요한 행동)과 같다.
- 단계의 행동이 모두 `DONE`이 되면 그 단계의 `completedAt`을 자동으로 채운다(`completedBy`는 null).
  `/steps/{id}/complete`는 행동이 없는 수동 단계나 실패한 행동을 오프라인으로 처리한 단계용이며,
  이미 완료된 단계는 409 `STEP_ALREADY_COMPLETED`다.
