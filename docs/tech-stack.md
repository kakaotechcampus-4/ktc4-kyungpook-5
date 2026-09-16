# 운영해 — 기술 스택 정리

`ai/README.md`, `be/README.md`, `fe/README.md`에서 **결정된 항목**을 모은 문서입니다.
세 저장소의 원본 README가 상세 근거를 가지며, 이 문서는 요약본입니다.

작성 기준일: 2026-09-16 / 세 파트 모두 **디렉터리 구조만 정의된 단계**(로직 미구현)입니다.

## 전체 구성

```text
FE (React SPA) ──REST──> BE (FastAPI) ──내부 API──> AI (FastAPI)
                          │                          │
                          ├─ PostgreSQL              └─ Anthropic LLM
                          └─ AWS S3
```

- FE는 BE만 호출하고, AI 서비스를 직접 호출하지 않습니다.
- AI는 계산이 필요하면 BE의 계산 API를 tool로 호출합니다 (AI가 직접 계산하지 않음).

## 확정된 기술 스택

### 공통

| 항목 | 선택 |
| --- | --- |
| API 프레임워크 | FastAPI (BE, AI 모두) |
| Python | 3.12 (BE·AI 통일) |
| Python 패키지 관리 | uv (`pyproject.toml` + `uv.lock`) |
| 챗봇 응답 방식 | 동기 — 스트리밍 미사용 (FE·AI 합의) |

### FE

| 항목 | 선택 |
| --- | --- |
| 프레임워크 | React (SSR·SEO 불필요 → Next.js 대신) |
| 빌드 도구 | Vite |
| 언어 | TypeScript |
| 스타일 | Tailwind |
| 라우팅 | React Router |
| 클라이언트 상태 | Zustand (전역), `useState` (화면 로컬) |
| HTTP 클라이언트 | axios |
| 린트 · 포맷 | ESLint + Prettier |

### BE

| 항목 | 선택 |
| --- | --- |
| DB | PostgreSQL (금액은 정수 원 단위로만 저장, NF2) |
| ORM | SQLAlchemy 2.0 |
| 마이그레이션 | Alembic |
| 파일 저장 | AWS S3 (`infra/s3.py`) — 영수증·기록 원본 |
| 배포 환경 | AWS EC2 + Docker Compose |
| 테스트 | pytest (`tests/unit`: 순수 함수 / `tests/integration`: 라우터 E2E) |
| 아키텍처 | 레이어드 (routers / schemas / services / models / db / core / infra) |

### AI

| 항목 | 선택 |
| --- | --- |
| LLM 제공자 | Anthropic |
| 실행 흐름 관리 | LangGraph |
| LLM 연동 구성요소 | LangChain 선택적 사용 (필요한 연동만) |
| 프롬프트 관리 | 기능별 `prompts/` — 처리 코드와 함께 관리 |
| 기능 분리 | `features/` (planning · retrieval · operations) + `workflow/` (분기·연결) |

## 확정된 API 규약 (FE ↔ BE)

- Base path: `/api/v1`
- 리소스 명명: 복수형 소문자 (`/events`)
- 응답 포맷: envelope 방식 — `{ "data": ..., "meta": ... }` (`meta`는 없으면 `null`, 필드는 항상 존재)
- 목록 조회 `meta`: `page`, `size`, `totalCount`
- 인증: `Authorization: Bearer <token>` (OAuth: Google · Kakao)
- 에러 포맷: `{ "error": { "code": "EVENT_NOT_FOUND", "message": "..." } }`
  - `code`는 `{도메인}_{문제}` 형태의 문자열 상수, FE가 `code` 기준으로 화면 문구를 매핑
  - `message`는 서버 기본 문구(로그·디버깅용)로 화면에 그대로 띄우지 않음
- `status` 등 상태값은 문자열 코드로 내려주고 표기 문구는 FE가 매핑
- 개인정보 필드(연락처 등)는 서버에서 마스킹되어 내려옴
- API 문서: FastAPI 자동 생성 Swagger + 노션 표로 스펙 공유

## 확정된 설계 원칙

### 공통

1. **결정론적 계산은 코드로** — 금액·정원·매칭·환불 판정은 `be/app/services/event_rules.py`의 순수 함수로 구현하고, 라우터·AI는 결과를 그대로 사용한다. LLM이 계산하거나 보정하지 않는다 (NF1).
2. **외부 영향 액션은 승인 후 실행** — 공지·예약·송금·환불은 `Approval` 레코드가 승인 상태일 때만 실행한다 (NF3).
3. **이력은 덮어쓰지 않는다** — Agent 호출·승인 이력은 수정·삭제 없이 새 레코드를 추가한다 (NF4).
4. **근거 제시 시 출처 포함** — 기록 기반 답변은 출처와 원문 위치를 포함하고, 근거가 없으면 없다고 답한다.

### FE

1. `pages/`는 조립만 한다. 로직은 `features/`로 옮긴다.
2. 컴포넌트에서 `fetch`를 직접 부르지 않는다. `features/*/hooks.ts`를 거친다. (서버 상태 라이브러리가 미정이어도 이 규칙은 먼저 고정)
3. `features/`끼리 import 하지 않는다. 공유는 `shared/`로 올린다.

### BE

- 라우터는 `services/`를 거쳐서만 모델과 계산을 조합한다. 다른 도메인의 `event_rules.py`·`models/`를 직접 끌어오지 않는다.

### AI

- 기능별 처리는 `features/`, 기능 간 연결·분기는 `workflow/`. 기능끼리 내부 구현을 직접 import 하지 않는다.

## 환경변수 (확정된 것)

| 파트 | 이름 | 용도 |
| --- | --- | --- |
| FE | `VITE_API_BASE_URL` | API 서버 주소 |
| BE | `DATABASE_URL` | PostgreSQL 연결 문자열 |
| BE | `AI_SERVICE_BASE_URL` | AI 내부 API 주소 |
| BE | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET_NAME` | S3 접근·버킷 |
| AI | `ANTHROPIC_API_KEY` | LLM 호출 인증 |
| AI | `ANTHROPIC_MODEL` | 사용할 모델 지정 |
| AI | `BACKEND_BASE_URL` | AI가 호출할 BE API 주소 |

세 파트 모두 `.env.example`만 커밋하고 실제 값이 든 `.env`는 커밋하지 않습니다.
변수명·필수 여부는 각 파트의 설정 코드 작성 시 확정합니다.

## 아직 미정 — 결정이 필요한 항목

| 항목 | 파트 | 내용 |
| --- | --- | --- |
| 서버 상태 관리 라이브러리 | FE | TanStack Query 유력, 미확정 |
| 테스트 도입 시점 | FE | 회비·예산 계산 유틸이 생기면 Vitest 도입 |
| FE 배포 위치 | FE | Docker 기반 방향만 확정, 서버·환경 미정 |
| 로컬 Docker Compose 범위 | FE · BE · AI | FE·AI를 컨테이너로 포함할지, BE/DB만 묶을지 |
| 인증 방식 | BE | JWT vs 세션 — `core/security.py`에서 구현, `JWT_SECRET_KEY`/`SESSION_SECRET` 변수도 이에 따라 결정 |
| RDS 병행 여부 | BE | EC2 + Docker Compose 배포에서 DB를 RDS로 뺄지 |
| 임베딩 저장 위치 | BE · AI | `records` 임베딩을 PostgreSQL(pgvector)에 둘지 Milvus를 쓸지 (BE는 메타데이터만 보유하는 안 포함) |
| S3 버킷 구조·접근 권한 | BE | 영수증 등 민감 파일 포함 — NF6(민감정보 최소 수집)과 연결 |
| 비동기 세션 사용 여부 | BE | SQLAlchemy 2.0 async 사용 여부 |
| 린트 · 포맷 도구 | BE · AI | 첫 구현에서 도구와 실행 명령 결정 |
| LLM 모델·버전 | AI | 제공자만 Anthropic으로 확정 |
| 계획 대화·체크포인트 저장 방식 | AI | 세션 식별자 포함 |
| 기록 검색·색인 방식 | AI | 자료 정제·색인·저장 방식 |
| 내부 API 계약 | BE · AI | 엔드포인트명·요청/응답 스키마, FE↔BE 세부 규칙(에러 포맷·페이지네이션 파라미터명·상태 코드별 처리) |

## 포함하지 않기로 한 것

- 챗봇 스트리밍 응답 (SSE/스트림 파싱)
- AI Trace · evaluation 구성
- LangChain 전체 패키지 직접 추가 (필요한 연동 패키지만)
