# 운영해 · Frontend

동아리 행사 보조 에이전트 "운영해"의 프론트엔드입니다.
아직 초기 세팅 단계이며, 실제 `npm create vite` 스캐폴딩 전에 폴더 구조와 컨벤션을 먼저 합의하기 위한 문서입니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 프레임워크 | **React** (확정) | SSR·SEO가 필요한 화면이 없어서(로그인 후 대시보드 중심) Next.js 대신 선택 |
| 빌드 도구 | Vite | React와 세트로 가장 무난한 선택 |
| 스타일 | **Tailwind** (확정) | — |
| 언어 | TypeScript | — |
| 라우팅 | React Router | — |
| 서버 상태 관리 | ⚠️ **미정** (TanStack Query 유력) | 라이브러리는 아직 확정 안 됐지만, **"컴포넌트에서 fetch 직접 호출 금지, `features/*/hooks.ts`의 훅을 거친다"는 규칙만 먼저 고정**한다. 구조 영향이 커서 라이브러리보다 규칙을 먼저 못 박음 |
| 클라이언트 상태 관리 | **Zustand** (확정) | 전역 상태(로그인 유저 정보 등)는 Zustand로 관리. 화면 로컬 상태는 여전히 `useState` 사용 |
| HTTP 클라이언트 | axios | — |
| 린트 · 포맷 | ESLint + Prettier | — |
| 테스트 | 초기 미적용 | 회비 · 예산 계산 같은 유틸 함수가 생기면 그 시점에 Vitest 도입 |
| 챗봇 응답 방식 | **동기(스트리밍 미사용)** (확정) | 답변을 한 번에 받아 표시. SSE/스트림 파싱 없이 axios로 단순 요청-응답만 구현하면 됨 |

### ❓ 확인이 필요한 항목 (팀에 질문)

- **[확인 필요] FE 배포 위치**: Docker 기반 배포로 방향은 잡았으나, 어느 서버/환경에 올릴지는 아직 미확정입니다.
- **[확인 필요] 로컬 Docker Compose 구성 시 FE도 포함할지**: 문서에 "Docker Compose로 묶는 것으로 사용(BE, FE 따로??)"라고 물음표로 남아있습니다. FE도 컨테이너로 띄울지, 로컬은 `npm run dev`로만 띄우고 BE/DB만 Compose로 묶을지 확인 필요합니다.

## 반드시 지켜야 할 3가지 규칙

1. `pages/`는 조립만 한다. 로직이 생기면 `features/`로 옮긴다.
2. 컴포넌트에서 `fetch`를 직접 부르지 않는다. `features/*/hooks.ts`를 거친다.
3. `features/`끼리 import 하지 않는다. 공유가 필요하면 `shared/`로 올린다.

## 폴더 구조

```
fe/
├── public/                      정적 파일 (파비콘 등). 빌드 시 그대로 복사됨
├── src/
│   ├── main.tsx                 진입점. 딱 5줄
│   ├── app/
│   │   ├── router.tsx           라우트 정의
│   │   ├── providers.tsx        QueryClient, 인증 컨텍스트 등 전역 래퍼
│   │   └── layout/
│   │       ├── AppLayout.tsx    상단바 + 사이드바 + 본문 자리
│   │       ├── Sidebar.tsx      메인/행사 계획/행사 목록/동아리 기록/마이 페이지
│   │       └── TopBar.tsx       로고 + 우측 영역
│   ├── pages/                   화면 하나당 파일 하나. 조립만 한다
│   │   ├── LoginPage.tsx
│   │   ├── SignupPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── PlanningPage.tsx
│   │   ├── EventListPage.tsx
│   │   ├── EventDetailPage.tsx
│   │   ├── RecordsPage.tsx
│   │   └── MyPage.tsx
│   ├── features/                실제 코드가 사는 곳
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── planning/
│   │   ├── events/
│   │   ├── approvals/
│   │   ├── ledger/
│   │   └── records/
│   │       ├── api.ts            서버 호출 함수 + 응답 타입
│   │       ├── hooks.ts          useXxx 커스텀 훅
│   │       ├── types.ts          도메인 타입
│   │       └── components/       해당 feature 전용 컴포넌트
│   ├── shared/                   여러 feature가 함께 쓰는 것
│   │   ├── ui/                   Button, Card, Chip, StepBar, ProgressBar
│   │   ├── api/
│   │   │   ├── client.ts         실제 fetch를 호출하는 유일한 곳
│   │   │   └── types.ts          공통 응답·에러 타입
│   │   ├── lib/                  format.ts, cn.ts
│   │   └── hooks/                useDisclosure.ts 등
│   └── styles/
│       └── index.css             Tailwind 지시문 + 전역 스타일
├── .env.example
├── .gitignore
├── index.html
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── vite.config.ts
```

> 위 하위 파일들은 현재 구조 확정을 위한 자리표시(placeholder)이며,
> 실제 내용은 `npm create vite`로 프로젝트를 스캐폴딩한 뒤 채워 넣을 예정입니다.

## 데이터가 흐르는 경로 (예: 승인 버튼)

```
ApprovalCard.tsx          버튼 클릭
  → hooks.ts              useApprove() 호출
  → api.ts                approveItem(id)
  → shared/api/client.ts  apiPost('/approvals/1/approve')
  → FastAPI
```

## API 관련 (BE와 합의된 사항, FE 구현 시 참고)

- Base path: `/api/v1`
- 리소스 명명: 복수형 소문자 (`/events`)
- 응답 포맷: **envelope 방식** (`{ "data": ..., "meta": ... }`) — raw로 안 감쌈
- 인증: `Authorization: Bearer <token>` 헤더 (OAuth: Google·Kakao)
- 개인정보 필드(연락처 등)는 서버에서 마스킹되어 내려옴
- API 문서: FastAPI 자동 생성 Swagger, FE와의 스펙 공유는 노션 표

> 위 항목들도 원본 문서(5장) 상 세부 규칙(에러 포맷, 페이지네이션 파라미터명, 상태 코드별 처리 등)이
> 아직 `___`로 비어 있는 부분이 많습니다. BE 쪽에서 5장이 마저 채워지면 이 문서에도 반영이 필요합니다.

## API 응답 포맷

### 1. 성공 응답 - 단건 조회
`GET /api/events/1`

\```json
{
  "data": {
    "id": 1,
    "name": "봄 MT",
    "status": "UPCOMING",
    "date": "2026-04-05"
  },
  "meta": null
}
\```

### 2. 성공 응답 - 목록 조회 (페이지네이션)
`GET /api/events?page=1&size=10`

\```json
{
  "data": [
    { "id": 1, "name": "봄 MT", "status": "UPCOMING", "date": "2026-04-05" },
    { "id": 2, "name": "가을 체육대회", "status": "ENDED", "date": "2025-10-12" }
  ],
  "meta": {
    "page": 1,
    "size": 10,
    "totalCount": 12
  }
}
\```

- `meta`가 없는 응답(단건 조회 등)은 `null`로 내려줌 (필드 자체는 항상 존재)
- 목록 조회는 `page`, `size`, `totalCount`
- `status`는 문자열 코드값으로 내려주고, 화면 표기 문구는 FE가 매핑

\```javascript
// status 예시
export const STATUS_LABELS: Record<string, string> = {
  UPCOMING: "예정",
  ONGOING: "진행중",
  ENDED: "종료",
};
\```

### 3. 에러 응답
\```json
{
  "error": {
    "code": "EVENT_NOT_FOUND",
    "message": "해당 행사를 찾을 수 없습니다."
  }
}
\```

- `code`: 문자열 상수. `{도메인}_{문제}` 형태로 네이밍 (예: `EVENT_NOT_FOUND`, `MEMBER_NOT_FOUND`)
- `message`: 서버 기본 문구(로그/디버깅용), FE는 이 값을 그대로 화면에 띄우지 않고 `code` 기준으로 자체 문구를 매핑

\```javascript
// 매핑 예시
export const ERROR_MESSAGES: Record<string, string> = {
  EVENT_NOT_FOUND: "해당 행사를 찾을 수 없어요.",
  UNAUTHORIZED: "로그인이 필요해요.",
  FORBIDDEN: "권한이 없어요.",
  VALIDATION_ERROR: "입력값을 다시 확인해주세요.",
};

export const DEFAULT_ERROR_MESSAGE = "일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.";
\```

## 환경변수

| 이름 | 용도 | 담당 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | API 서버 주소 | 박수겸 |

`.env.example`은 커밋하고, 실제 값이 든 `.env`는 커밋하지 않습니다.
