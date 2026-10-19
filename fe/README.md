# 운영해 Frontend

React 19 · TypeScript · Vite 6 · Tailwind 4 · TanStack Query 5 · Zustand · axios 기반입니다.

## 로컬 실행

```sh
cd fe
npm ci
cp .env.example .env
npm run dev
```

`.env.example`의 `VITE_API_BASE_URL=http://localhost:8000`을 실제 BE 주소로 맞춥니다. 주소는 `/api/v1`을 제외한 origin이며 Vite 프록시는 없습니다. FE/BE를 별도 포트로 실행하면 BE CORS에서 FE origin을 허용해야 합니다. localhost·HTTPS에서 마이크와 Service Worker를 사용할 수 있습니다. 실제 `.env`는 Git 제외입니다.

이번 로컬 병렬 검증은 기존 Docker5173/BE8000을 보존하고 FE5175→BE8001을 사용했습니다. 이 포트는 제품 고정값이 아닙니다.

## 회의 베타

`/login`에서 실제 로그인하고 `/me`가 반환한 소속을 선택합니다. `/meetings`에서 자료와 회의를 준비하고 `/meetings/:meetingId`에서 확정 전사·자료 답/출처·일정/할 일 후보를 확인합니다. 후보의 내용·담당자·정확한 시각·별도 수신 계정을 확인한 뒤 저장·예약합니다. 서버가 권한·조직·버전·예약을 판단합니다.

- 자료의 `COMPLETED`는 파싱 완료, `INDEXED`만 검색 준비 완료입니다. 실제 실패를 fixture로 대체하지 않습니다.
- 마이크는 WS 서버의 `audio.ready` 이후 켭니다. mono PCM16LE 16kHz 연속 음성을 전송하며 VAD·STT는 서버가 맡습니다. 마지막 음성 전송·`audio.end_ack`·`audio.completed`를 구분합니다.
- PWA manifest·Service Worker가 있습니다. 사용자가 알림을 허용하고 본인 기기의 Push 구독을 등록합니다. 서버 Push 접수와 기기 시스템 알림 표시는 다릅니다. 알림을 누르면 소속을 확인하고 실제 확정 항목을 다시 조회합니다.
- 개발 서버에서만 `/meetings?fixture=1`로 명시적 예시를 볼 수 있습니다. 실제 저장·음성·예약·알림은 생성하지 않습니다. 기존 다른 화면의 `?demo` 규칙과 별개입니다.
- 회원가입·행사/계획/마이페이지 전체의 실연동 완료를 뜻하지 않습니다. 이번 범위는 기존 로그인과 회의 베타 연결입니다.

서버에 실제 STT/AI 모델 설정이 필요합니다. 설정이 없거나 API가 실패하면 오류를 표시합니다. 자동 WS 재접속·모바일 백그라운드 녹음·전체 오프라인 캐시는 이번 범위가 아닙니다.

## 개발 규칙

`pages`는 조립, 통신은 `features`의 hook → api → `shared/api/client`를 사용합니다. features 간 import를 만들지 않습니다. 소속·세션은 기존 shared Zustand를 재사용하고 공통 UI는 `/dev/ui`에서 확인합니다.

```sh
npm run build
npm run lint
node --test tests/*.test.mjs
node --experimental-transform-types --test src/features/meetings/audio/pcm.test.mjs
```

## API 타입

생성 파일 `src/shared/api/schema.d.ts`는 손으로 수정하지 않습니다.

```sh
npm run gen:api-types
npm run gen:api-types -- /path/to/openapi.json
OPENAPI_SOURCE=http://127.0.0.1:8001/openapi.json npm run gen:api-types
```

기본 source는 `http://localhost:8000/openapi.json`입니다. API 응답은 `{data, meta}`, 인증은 opaque Bearer 세션입니다. 에러의 `code`로 화면 문구를 매핑합니다.

자료 API·제약은 [자료 연결](docs/records-integration.md), Push payload와 상태는 [알림 연결](docs/meeting-push-contract.md), 오디오 순서와 마지막 프레임은 [음성 adapter](src/features/meetings/audio/README.md)를 참고합니다.

## 기존 개발 기준 문서

# 운영해 · Frontend

동아리 행사 보조 에이전트 "운영해"의 프론트엔드입니다.
화면은 대부분 구현돼 있고 서버 연동이 남았습니다. 어느 화면이 어느 API에 붙는지는
`docs/week10/fe/운영해_FE_연동_기준서.md`를 봅니다.

```bash
npm install
npm run dev            # http://localhost:5173
npm run build          # tsc -b && vite build
npm run lint
npm run gen:api-types  # BE가 localhost:8000에 떠 있어야 한다
```

서버 없이 화면만 보려면 주소에 `?demo`를 붙입니다(예: `/planning?demo`).
붙이지 않으면 빈 상태 화면이 나옵니다.

## 기술 스택

| 항목 | 선택 | 결정 이유 / 메모 |
| --- | --- | --- |
| 프레임워크 | **React** (확정) | SSR·SEO가 필요한 화면이 없어서(로그인 후 대시보드 중심) Next.js 대신 선택 |
| 빌드 도구 | Vite | React와 세트로 가장 무난한 선택 |
| 스타일 | **Tailwind** (확정) | — |
| 언어 | TypeScript | — |
| 라우팅 | React Router | — |
| 서버 상태 관리 | **TanStack Query** (확정) | **"컴포넌트에서 fetch 직접 호출 금지, `features/*/hooks.ts`의 훅을 거친다"는 규칙**이 먼저이고 라이브러리는 그 뒤다 |
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
├── public/                      정적 파일. 빌드 시 그대로 복사됨
├── src/
│   ├── main.tsx                 진입점
│   ├── app/
│   │   ├── router.tsx           라우트 정의
│   │   ├── providers.tsx        QueryClient 등 전역 래퍼
│   │   └── layout/AppLayout.tsx 상단바 + 본문 자리
│   ├── pages/                   화면 하나당 파일 하나. 조립만 한다
│   │   ├── LoginPage.tsx  SignupPage.tsx
│   │   ├── MainPage.tsx                     M1 메인
│   │   ├── PlanningPage.tsx  PlanStepsPage.tsx    P1 · P2
│   │   ├── EventListPage.tsx  EventDetailPage.tsx  EventCancelPage.tsx
│   │   ├── MyPage.tsx                       내 정보 · 동아리원 · 자료
│   │   ├── DevUiPage.tsx                    /dev/ui — 공용 컴포넌트 모아보기
│   │   └── NotFoundPage.tsx
│   ├── features/                실제 코드가 사는 곳
│   │   ├── auth/                components, mock, types
│   │   ├── dashboard/           components, hooks, mock, types
│   │   ├── events/              api, components, hooks, mock, types
│   │   ├── mypage/              components, mock, types
│   │   └── planning/            catalogue, components, mock, types
│   ├── shared/                  여러 feature가 함께 쓰는 것
│   │   ├── ui/                  Button, Card, Chip, Modal, Toast, Tori, StateScreen …
│   │   ├── api/
│   │   │   ├── client.ts        axios를 쓰는 유일한 곳
│   │   │   ├── models.ts        schema.d.ts의 긴 경로에 이름만 붙인 곳
│   │   │   ├── schema.d.ts      BE openapi.json에서 생성. 손으로 고치지 않는다
│   │   │   └── types.ts         공통 응답·에러 타입
│   │   ├── auth/                로그인 사용자 전역 상태(zustand)
│   │   └── lib/                 format, labels, cn, dialog, toast, clipboard
│   └── styles/index.css         디자인 토큰(@theme) + 전역 스타일
├── .env.example
├── .prettierrc  .prettierignore  eslint.config.js
├── index.html  package.json  vite.config.ts
└── tsconfig.json  tsconfig.app.json  tsconfig.node.json
```

> `features/`에 `api.ts`·`hooks.ts`가 다 있지는 않습니다. 아직 서버에 붙지 않은
> feature는 `mock.ts`만 두고, 연동할 때 그 둘을 추가합니다.

## 데이터가 흐르는 경로 (예: 승인 버튼)

```
ActionCard.tsx                        버튼 클릭
  → features/events/hooks.ts          useApproveAction() 호출
  → features/events/api.ts            approveAction(actionId)
  → shared/api/client.ts              apiPost('/actions/act_21/approve')
  → FastAPI
```

> 승인·거절 경로는 아직 BE에 없습니다(#41). 위는 붙을 자리를 보이는 예시입니다.

## API 관련 (BE와 합의된 사항, FE 구현 시 참고)

- Base path: `/api/v1`
- 리소스 명명: 복수형 소문자 (`/events`)
- 응답 포맷: **envelope 방식** (`{ "data": ..., "meta": ... }`) — raw로 안 감쌈
- 인증: `Authorization: Bearer <token>` 헤더 (OAuth: Google·Kakao)
- 개인정보 필드(연락처 등)는 서버에서 마스킹되어 내려옴
- API 문서: FastAPI 자동 생성 Swagger(`http://localhost:8000/docs`)

> 어느 화면이 어느 API에 붙고 무엇이 아직 없는지는 `docs/week10/fe/운영해_FE_연동_기준서.md`에 있습니다.
> 행사 계획(P1·P2)의 계약은 `be/app/ai/contracts.py`가 기준입니다.

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
