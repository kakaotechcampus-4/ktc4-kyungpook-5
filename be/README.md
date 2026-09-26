# 운영해 · BE

현재는 **ORM 모델과 mock API 1개까지 구현한 단계**입니다. DB 연결·인증·규칙 엔진은 아직 없습니다.
mock API는 DB 없이 고정 응답만 내려 FE가 화면을 실제 API에 붙여볼 수 있게 한 것입니다 (이슈 #30).
모델 확정 내역과 그 근거는 [BE 스키마 검토안](../docs/week6/be/운영해_BE_스키마_검토안.md)에 있습니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 언어 | Python 3.12 | AI와 통일 |
| API 프레임워크 | FastAPI | FE와 AI가 호출하는 API 서버 |
| DB | PostgreSQL | 금액은 정수 원 단위로만 저장 (NF2) |
| ORM | SQLAlchemy 2.0 | 비동기 세션 사용 여부는 구현 시 결정 |
| 마이그레이션 | Alembic | DB가 아직 없어 리비전을 만들지 않았습니다. 첫 배포 직전에 초기 리비전 하나를 만듭니다 |
| 파일 저장 | AWS S3 (`infra/s3.py`) | 영수증·기록 원본 업로드 |
| 패키지 관리 | uv | AI와 동일하게 `pyproject.toml` 기반 |
| 인증 | 미정 | JWT vs 세션 등 방식 확정 전, `core/security.py`에서 구현 |
| 배포 환경 | AWS EC2 + Docker Compose | RDS 병행 여부 미정 |
| 테스트 | pytest | `tests/unit`은 `event_rules.py` 순수 함수, `tests/integration`은 라우터 엔드투엔드 |
| 린트 · 포맷 | 미정 | 첫 구현에서 도구와 실행 명령 결정 |

### 확인이 필요한 항목

- FE 명세 반영이 필요한 5건 — [검토안 §4](../docs/week6/be/운영해_BE_스키마_검토안.md)
- 회의·확인이 필요한 항목 — [검토안 §5](../docs/week6/be/운영해_BE_스키마_검토안.md)
- `participants` · `transactions` 테이블 — 금액 안건 확정 후 추가
- FE/AI 내부 API의 엔드포인트명과 요청·응답 스키마
- RAG 원본·근거 데이터(`records`)를 BE의 PostgreSQL에 메타데이터만 둘지, 임베딩까지 함께 둘지 (Milvus vs pgvector)
- S3 버킷 구조와 접근 권한 — 영수증 등 민감 파일이 포함되어 NF6(민감정보 최소 수집)과 연결됨

## 반드시 지켜야 할 규칙

1. 금액·정원·매칭·환불 판정 같은 결정론적 계산은 `services/event_rules.py`의 순수 함수로 구현한다. 라우터와 AI 서비스는 이 결과를 그대로 받아 쓸 뿐, 계산을 직접 하거나 보정하지 않는다 (NF1).
2. 공지·예약·송금·환불 등 외부에 영향을 주는 액션은 `Approval` 레코드가 승인 상태로 존재할 때만 실행한다. 승인 레코드 없이 실행되는 코드 경로를 두지 않는다 (NF3).
3. Agent 호출 이력과 승인 이력은 빠짐없이 기록하고 수정·삭제하지 않는다. 상태가 바뀌면 새 레코드를 추가해 이전 상태를 덮어쓰지 않는다 (NF4).
4. 라우터는 `services/`를 거쳐서만 모델과 계산을 조합한다. 다른 도메인의 `event_rules.py`나 `models/`를 직접 끌어와 우회하지 않는다.

## 폴더 구조

```text
be/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
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
│   │   └── records.py       # 동아리 기록 업로드·조회
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── clubs.py
│   │   ├── events.py
│   │   └── records.py
│   ├── models/
│   │   ├── __init__.py        # 전 모델 등록 (Base.metadata)
│   │   ├── auth.py            # Auth
│   │   ├── clubs.py           # Club · Member
│   │   ├── events.py          # Event · Step · Action
│   │   ├── records.py         # Record
│   │   ├── agent.py           # AgentLog
│   │   └── chat.py            # Conversation · Message
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── club_service.py
│   │   ├── event_service.py   # 계획/참가자/승인/업무 오케스트레이션
│   │   ├── event_rules.py     # 참가비·환불·정산 계산 순수함수 (규칙 엔진, NF1)
│   │   └── record_service.py
│   └── infra/
│       ├── s3.py
│       └── agent_client.py    # AI 서비스 호출 클라이언트
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
| `infra` | AI 서버, S3 등 외부 연동 |

## 모듈별 담당 범위

| 모듈 | 담당 | 예시 |
| --- | --- | --- |
| `services/event_rules.py` | 참가비·환불·정산 등 결정론적 계산 (순수 함수, NF1) | 확정 인원 39명, 최소 인원 40명 → 미달 판정 |
| `routers/*` | FE·AI가 호출하는 REST 엔드포인트, 요청 검증 | `POST /events/{id}/participants/{id}/cancel` (`routers/events.py`) |
| `services/event_service.py` | 계산 결과와 모델 변경을 하나의 트랜잭션으로 조합 (오케스트레이션) | 취소 처리 시 환불 판정 + 인원 재계산 + 후속 질문 생성을 함께 커밋 |
| `infra/agent_client.py` | AI 내부 API 호출 | 취소로 인한 영향 설명·대응안 생성을 AI에 요청 |
| `infra/s3.py` | 영수증·기록 원본 파일 업로드·조회 | 지출 등록 시 영수증 이미지를 S3에 올리고 URL을 `expense`에 저장 |

`services/event_rules.py`는 AI(`tools/accounting.py` 등)가 tool로 호출하는 계산이기도 합니다. AI가 임의로 계산하지 않고 이 결과를 그대로 받아 쓰도록, 이 경계는 API 계약으로도 명시합니다.

## 데이터가 흐르는 경로 (예: 참가자 취소)

```text
요청 → routers/events.py (취소 엔드포인트)
        → services/event_rules.py: 환불 규칙·기한 경계 판정, 최소 인원 재계산
        → services/event_service.py: 판정 결과 반영 + 후속 질문 레코드 생성 (하나의 트랜잭션)
        → infra/agent_client.py: 영향 설명·대응안 생성 필요 시 AI 호출
   ← 환불 판정 + 영향 + 후속 질문을 함께 응답
```

실제 분기와 AI 호출 시점은 기능 구현 시 구체화합니다.

## API 연동

BE는 두 방향에서 호출됩니다.

- **FE → BE**: 행사 생성, 질문·답변, 대안 비교, 승인, 수납 대조, 취소·환불, 정산 조회 등 서비스의 주 REST API(`routers/clubs.py`, `routers/events.py`, `routers/records.py`).
- **AI → BE**: AI의 `tools/`가 호출하는 계산·조회용 내부 API(참가비·환불 계산, 매칭, 행사 상태 조회 등). 엔드포인트와 스키마는 AI 팀과 별도로 확정합니다.

공통 요청·응답 형식은 `app/schemas/`에서 라우터별로 관리하고, 에러 응답 형식(예: `MINIMUM_HEADCOUNT_VIOLATED`, `APPROVAL_REQUIRED`)은 `core/exceptions.py`를 통해 전 엔드포인트에서 동일한 구조를 씁니다.

## 데이터 모델

테이블 10개를 여섯 파일로 나눕니다.

| 파일 | 테이블 |
| --- | --- |
| `models/clubs.py` | `clubs` · `members` |
| `models/auth.py` | `auth` |
| `models/events.py` | `events` · `steps` · `actions` |
| `models/records.py` | `records` |
| `models/agent.py` | `agent_log` |
| `models/chat.py` | `conversations` · `messages` |

공통 컬럼과 공유 컬럼 타입은 `db/base.py`에 있습니다. 모든 테이블이 `id`(접두어가 붙은 26자 문자열 PK)와
`created_at` · `modified_at`을 가집니다.

별도의 `Approval` 테이블은 두지 않습니다. 승인 대상은 `actions`이며 `status`와 `approve_needed`로
관리합니다. 다만 `status`를 덮어쓰는 현재 구조는 NF4와 어긋나므로, 승인 이력 테이블은 승인 정책이
확정된 뒤 별도로 추가합니다.

## 환경변수

| 이름 | 용도 | 상태 |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL 연결 문자열 | 변수명·값 확정 예정 |
| `AI_SERVICE_BASE_URL` | `infra/agent_client.py`가 호출할 AI 내부 API 주소 | 변수명·값 확정 예정 |
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

`.env`의 DB 연결 정보, AI 서비스 주소, S3 접근 정보를 로컬 환경에 맞게 설정하세요. 기존 `.env`는 덮어쓰지 않습니다.

로컬 PostgreSQL은 Docker Compose로 띄우는 것을 기본으로 하되, 구체적인 compose 구성은 첫 구현 시 추가합니다.
아래 mock API는 DB에 접속하지 않으므로 `.env` 설정 없이도 실행됩니다.

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

서버를 띄우지 않고 `TestClient`로 앱을 직접 호출하므로 DB·`.env` 없이 실행됩니다.
`tests/integration/`은 mock API의 응답 계약(`{data, meta}` 봉투, camelCase 키, enum 문자열,
에러 봉투)을 고정합니다. 공통 코드(`schemas`의 `CamelModel`, `core/exceptions.py`)를 바꿀 때
이 테스트가 먼저 깨지도록 두는 것이 목적입니다 (이슈 #33).

AI 모듈 테스트(`app/ai/tests/`)도 같은 명령으로 함께 실행됩니다.

## mock API

| 엔드포인트 | 상태 |
| --- | --- |
| `GET /api/v1/events/{eventId}/actions` | 구현 완료 |
| `GET /api/v1/events` | 미구현 |
| `GET /api/v1/events/{eventId}/steps` | 미구현 |

**유효한 `eventId`는 `evt_9f2c8a` 하나뿐입니다.** 다른 값은 404 `EVENT_NOT_FOUND`를 반환합니다.

```bash
# M1 승인 대기 (확인 요청 제외)
curl "localhost:8000/api/v1/events/evt_9f2c8a/actions?status=PENDING&excludeType=CONFIRMATION"

# L2 처리된 승인
curl "localhost:8000/api/v1/events/evt_9f2c8a/actions?status=APPROVED,DONE,DENIED"

# L2 확인 요청
curl "localhost:8000/api/v1/events/evt_9f2c8a/actions?type=CONFIRMATION"
```

mock 단계의 한계입니다.

- 인증이 없어 `canApprove`는 항상 `true`입니다.
- `amount`는 컬럼이 있는데도 전건 `null`입니다. 이슈 #30의 합의를 따른 것이며, FE가 금액 표시를 검증해야 하면 채웁니다.
- 확인 요청의 `options` / `allowManual`은 `actions.payload`(JSONB)에 담아 응답에서 펼칩니다. `type=CONFIRMATION`인 건에만 값이 있고 나머지는 `null`입니다.
- fixture는 `app/services/event_service.py`에 있습니다. DB 연결 시 `list_actions()` 본문만 쿼리로 교체하면 라우터·스키마는 그대로 씁니다.
