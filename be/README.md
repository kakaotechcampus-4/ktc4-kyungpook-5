# 운영해 · BE

현재는 **디렉터리 구조를 정의한 단계**입니다. 라우터·모델·규칙 엔진은 아직 구현되지 않았습니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 언어 | Python 3.12 | AI와 통일 |
| API 프레임워크 | FastAPI | FE와 AI가 호출하는 API 서버 |
| DB | PostgreSQL | 금액은 정수 원 단위로만 저장 (NF2) |
| ORM | SQLAlchemy 2.0 | 비동기 세션 사용 여부는 구현 시 결정 |
| 마이그레이션 | Alembic | 도입 여부·시점 미정 |
| 파일 저장 | AWS S3 (`infra/s3.py`) | 영수증·기록 원본 업로드 |
| 패키지 관리 | uv | AI와 동일하게 `pyproject.toml` 기반 |
| 인증 | 미정 | JWT vs 세션 등 방식 확정 전, `core/security.py`에서 구현 |
| 배포 환경 | AWS EC2 + Docker Compose | RDS 병행 여부 미정 |
| 테스트 | pytest | `tests/unit`은 `event_rules.py` 순수 함수, `tests/integration`은 라우터 엔드투엔드 |
| 린트 · 포맷 | 미정 | 첫 구현에서 도구와 실행 명령 결정 |

### 확인이 필요한 항목

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
│   │   └── deps.py
│   ├── db/
│   │   ├── base.py
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
│   │   ├── auth.py
│   │   ├── clubs.py
│   │   ├── events.py
│   │   └── records.py
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

`.gitignore`, `README.md`, (uv 사용 시) `uv.lock`은 위 구조에 그대로 추가하면 됩니다. 빈 폴더는 `.gitkeep`으로 유지합니다.

레이어드 아키텍처로 역할을 나누고, 레이어 내부는 인증(`auth`)·동아리(`clubs`)·행사(`events`)·기록(`records`) 도메인별로 파일을 나눕니다.

| 레이어 | 역할 |
| --- | --- |
| `routers` | 요청을 받는 API 엔드포인트 |
| `schemas` | Pydantic 기반 요청·응답 데이터 형식 |
| `services` | 비즈니스 로직 구현 |
| `models` | DB 테이블과 매핑되는 ORM 모델 |
| `db` | DB 연결과 세션 관리 |
| `core` | 설정, 인증, 에러 처리 등 공통 모듈 |
| `infra` | AI 서버, S3 등 외부 연동 |

현재는 폴더 구조와 빈 파일 스텁까지만 작업했고, 로직 구현·DB 연결·인증 처리는 포함하지 않습니다.

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

모델은 라우터와 같은 경계로 `models/auth.py`, `models/clubs.py`, `models/events.py`, `models/records.py`로 나눕니다. `events.py`에는 계획·참가자·결제·지출·승인·업무 관련 테이블이 함께 들어가므로, 파일 하나가 커지면 클래스 단위로 섹션을 나눠 관리합니다. 승인(`Approval`)·Agent 실행 로그(`AgentRun`)를 이 파일에 포함할지 별도로 분리할지는 위 확인 필요 항목에 남겨뒀습니다.

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

로컬 PostgreSQL은 Docker Compose로 띄우는 것을 기본으로 하되, 구체적인 compose 구성은 첫 구현 시 추가합니다. 현재는 의존성 설치만 가능하며 FastAPI 앱과 DB 연결이 구현되지 않아 서버 실행 명령은 제공하지 않습니다.
