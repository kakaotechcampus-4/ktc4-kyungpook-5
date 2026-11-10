# 운영해 · Frontend

동아리 운영진을 위한 AI 행사 보조 서비스 **운영해**의 웹 프론트엔드입니다.
운영진은 AI 도우미 **토리**와 대화하며 행사를 계획하고, 대면 회의 중에는 토리가 과거 기록에서 찾은 답을 출처와 함께 받습니다.
토리는 제안만 합니다. 계획 확정, 공지·이체 같은 행동의 승인, 할 일 알림 예약은 운영진이 확인한 뒤에만 일어납니다.

- 배포: https://unyounghae.kro.kr (PWA 설치 가능)
- 설계와 구현 상세: [FE 기술 문서](docs/technical-overview.md)

## 주요 화면

| 경로 | 화면 | 하는 일 |
| --- | --- | --- |
| `/` | 소개 | 서비스 소개. 로그인 상태면 메인으로, 아니면 로그인으로 안내 |
| `/dashboard` | 메인 | 토리 브리핑(확인할 일, 진행·계획 중인 행사), 토리에게 묻고 카드로 답 받기(자료·할 일·승인 대기·행사 현황·회의 할 일) |
| `/planning` | 행사 계획 P1·P2 | 토리와 대화해 조건 정하기 → 계획 초안 생성 → 단계·행동 검토·수정 → 운영 시작 |
| `/events`, `/events/:id`, `/events/:id/cancel` | 행사 목록·상세·취소 | 진행 단계와 지금 할 일, 토리가 쓴 공지·발송 초안 검토·승인, 운영 중 상황 대응, 취소 뒷정리 |
| `/meetings`, `/meetings/:id` | 회의 | 녹음 중 전사와 토리 답(출처 포함) → 종료 후 화자 확인, 일정·할 일 후보 확인·저장·알림 예약. 기기 알림 켜기 |
| `/records` | 자료함 | 회칙·장부·결과보고(PDF·CSV·XLSX) 업로드, 처리 상태 확인, 검색 |
| `/accounting` | 회계 | 영수증 사진으로 지출 등록, 장부 입력·수정, 지출에 행사 연결 |
| `/mypage` | 마이페이지 | 내 정보, 동아리원 명단·초대, 동아리 정보 수정, 동아리 자료 |
| `/login`, `/signup`, `/clubs/new`, `/clubs/join` | 인증·동아리 | 회원가입, 이메일·카카오 로그인, 동아리 만들기, 초대 코드로 참여 |
| `/onboarding` | 체험 | 실제 API 없이 예시 계정으로 회의 → 후보 저장 흐름 체험 |

## 기술 스택

| 영역 | 선택 | 이유 |
| --- | --- | --- |
| 프레임워크 | React 19 + TypeScript | 로그인 뒤 쓰는 대시보드형 앱이라 SSR·SEO가 필요 없음 |
| 빌드 | Vite 6 | 빠른 개발 서버, 정적 파일 빌드 |
| 스타일 | Tailwind CSS 4 | 디자인 토큰을 `src/styles/index.css`의 `@theme`에 모음 |
| 서버 상태 | TanStack Query 5 | 캐시·재조회·폴링(회의 타임라인, 자료 처리 상태)을 한 방식으로 처리 |
| 전역 상태 | Zustand 5 | 로그인 세션·선택한 소속, 녹음 중 잠금, 토스트처럼 여러 화면이 함께 보는 상태만 전역에 둠. 화면 상태는 `useState` |
| HTTP | axios + fetch | 일반 요청은 axios, 응답을 조금씩 읽어야 하는 SSE는 fetch |
| 라우팅 | React Router 7 | 공통 레이아웃을 중첩 라우트로 공유하고, 녹음 중 화면 이동을 `useBlocker`로 막음 |
| API 타입 | openapi-typescript | BE OpenAPI에서 `schema.d.ts`를 생성해 요청·응답 타입을 맞춤 |
| 음성 | Web Audio API(AudioWorklet), WebSocket | 브라우저에서 PCM16 16kHz로 바꿔 서버로 전송 |
| 알림 | Service Worker + Web Push | PWA 설치, 기기 알림 |
| 배포 | Docker(멀티 스테이지) + Caddy | 정적 파일 서빙, `/api/*`는 BE로 프록시, HTTPS 자동 발급 |

## 시작하기

Node 22를 씁니다(CI·배포 이미지와 같은 버전).

```bash
cd fe
npm ci
cp .env.example .env
npm run dev   # http://localhost:5173
```

| 환경변수 | 용도 |
| --- | --- |
| `VITE_API_BASE_URL` | BE origin(예: `http://localhost:8000`). `/api/v1`은 빼고 적습니다. Vite 프록시는 없습니다 |
| `VITE_KAKAO_REST_API_KEY` | 카카오 로그인용 REST API 키. 리디렉션 URI는 `<FE origin>/auth/kakao/callback`이고, 카카오·BE에 등록한 값과 같아야 합니다 |

- BE CORS는 기본으로 `http://localhost:5173`·`http://127.0.0.1:5173`만 허용합니다. FE를 다른 주소로 띄우면 BE 환경변수 `CORS_ORIGINS`에 추가합니다.
- 마이크와 Service Worker는 localhost나 HTTPS에서만 동작합니다.
- 저장소 루트에서 `docker compose up`으로 PostgreSQL·BE·FE를 함께 띄울 수도 있습니다. DB 마이그레이션 등 BE 쪽 준비는 [`be/README.md`](../be/README.md)를 봅니다.

## 명령어

```bash
npm run dev              # 개발 서버
npm run build            # 타입 검사(tsc -b) + 빌드
npm run lint             # ESLint
node --test tests/*.test.mjs src/shared/api/sse.test.mjs   # 단위 테스트(node:test)
npm run gen:api-types    # BE OpenAPI → src/shared/api/schema.d.ts
```

- `gen:api-types`의 기본 source는 `http://localhost:8000/openapi.json`입니다. 다른 곳에서 받으려면 `npm run gen:api-types -- <파일 경로나 주소>`나 `OPENAPI_SOURCE=<주소> npm run gen:api-types`를 씁니다.
- `schema.d.ts`는 생성 파일이라 손으로 고치지 않습니다.
- 회의 음성 변환 테스트: `node --experimental-transform-types --test src/features/meetings/audio/pcm.test.mjs`
- `tests/e2e/`는 Playwright로 화면을 돌려 보는 스크립트입니다. `npm install --no-save playwright`가 필요하고, 개발 서버·가짜 API·합성 DB 중 무엇이 필요한지는 파일 머리말에 있습니다.

## 폴더 구조

```text
src/
├── app/            라우터, 전역 Provider, 레이아웃(상단바·사이드 메뉴)
├── pages/          화면 하나당 파일 하나
├── features/       도메인별 코드
│   ├── planning/       행사 계획 P1·P2 (SSE 스트림, 생성 요청 복구)
│   ├── meetings/       회의 (audio/: 마이크 → PCM → WebSocket)
│   ├── events/         행사 목록·상세, 행동 초안·승인·실행, 운영 상황 대응
│   ├── dashboard/      메인 브리핑, 토리 대화(카드 답)
│   ├── records/        자료 업로드·검색
│   ├── accounting/     영수증 가져오기, 장부
│   ├── notifications/  Push 구독, 알림 설정
│   ├── auth/ clubs/ mypage/ onboarding/ home/
│   └── <domain>/{types,api,hooks}.ts + components/
├── shared/
│   ├── api/        client.ts(HTTP 유일 통로), sse.ts, schema.d.ts(생성), models.ts
│   ├── auth/       세션·토큰·소속 전역 상태(Zustand)
│   ├── pwa/        Service Worker 등록
│   ├── ui/         Button, Card, Modal, Toast, StateScreen, Tori …
│   └── lib/        labels(enum→문구), format, toast, dialog …
└── styles/index.css   디자인 토큰 + 전역 스타일
public/
├── sw.js                    Push 표시·클릭 처리
├── meeting-pcm-worklet.js   마이크 입력을 mono로 모으는 AudioWorklet
├── rnnoise/                 노이즈 억제 wasm(현재 화면에서는 꺼 둠)
└── manifest.webmanifest
```

## 개발 규칙

1. `pages/`는 조립만 합니다. 로직이 생기면 `features/`로 옮깁니다.
2. 컴포넌트는 `fetch`·axios를 직접 부르지 않습니다. `features/<domain>/hooks.ts` → `api.ts` → `shared/api/client.ts` 순서로 거칩니다.
3. `features/`끼리 import하지 않습니다. 함께 쓸 것은 `shared/`로 올립니다.
4. 서버의 enum은 `shared/lib/labels.ts`에서 화면 문구로 바꿉니다. 오류는 서버 `message`를 그대로 띄우지 않고 `code`로 문구를 고릅니다.
5. 실패를 빈 결과나 예시 데이터로 덮지 않습니다. 처리하지 못한 사실과 다시 할 수 있는 일을 보여 줍니다.

> 1·3·4번은 아직 지키지 못한 곳이 남아 있습니다. 행사 상세 페이지에 로직이 있고, 메인·계획·회의 등이 다른 feature의 컴포넌트·타입을 가져다 씁니다. 새 코드는 규칙을 따르고, 기존 예외는 고칠 때 `shared/`로 옮깁니다.

### API 규약

- Base path `/api/v1`, 응답은 `{ data, meta }` 봉투, 오류는 `{ error: { code, message } }`
- 인증은 `Authorization: Bearer <accessToken>`. 401이 오면 `client.ts`가 refresh를 한 번만 시도합니다.
- 화면에서 본 버전을 `expectedVersion`·`baseRevision`으로 함께 보냅니다. 그사이 바뀌었으면 서버가 409로 거절하고, 화면은 다시 불러와 확인하게 합니다.
- 계획 대화·생성 요청에는 `Idempotency-Key`를 붙입니다. 연결이 끊겨도 같은 요청을 다시 보내지 않고 결과만 조회합니다.

## 개발용 보기

| 방법 | 내용 |
| --- | --- |
| `?demo` | `/dashboard`, `/planning`, `/events`, `/mypage`에서 서버 없이 예시 데이터로 화면을 봅니다 |
| `/meetings?fixture=1` | 개발 서버에서만 회의 예시 화면을 봅니다(`&ended=1`이면 종료 화면). 저장·음성·예약·알림은 만들지 않습니다 |
| `/onboarding` | 예시 계정 체험. 인증·자료·회의 API와 마이크·Push 권한을 쓰지 않습니다. 진행 상태는 localStorage `unyounghae_onboarding_preview_v2`에만 둡니다 |
| `/dev/ui` | 공용 UI 컴포넌트 모아 보기 |

## 배포

`develop`을 향한 PR과 `develop` push마다 GitHub Actions(`.github/workflows/deploy.yml`)가 `npm ci → lint → build`로 검증합니다. `develop` push일 때만 이어서 `Dockerfile.prod`로 이미지를 만들어 배포합니다.
이미지는 Vite 빌드 결과를 Caddy로 서빙하고, `/api/*`는 API 컨테이너로 넘기며, 그 밖의 경로는 `index.html`로 돌려 SPA 라우팅을 처리합니다.
EC2 반영 절차는 [`deploy/README.md`](../deploy/README.md)를 봅니다.

## 더 읽을 문서

- [FE 기술 문서](docs/technical-overview.md): 구조, 기능별 구현, 토리가 자동으로 하는 일, 핵심 기술 결정
- [BE API Reference](../be/docs/api-reference.md): 도메인별 엔드포인트·권한·공통 규칙
- [배포 절차](../deploy/README.md): EC2 배포와 운영자 확인 사항
