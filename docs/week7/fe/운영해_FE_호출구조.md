# 운영해 · FE 호출 구조

> 신규 진입자용. "파일 하나 고치려는데 어디부터 봐야 하는지" 답하는 문서.

---

## 레이어

```
pages/<Screen>Page.tsx        조립만. 로직 없음
  └─ features/<domain>/
       hooks.ts               state + 이 화면이 하는 동작(핸들러)
       api.ts                 서버 호출 함수. 명세 그대로, BE 없으면 목업 반환
       types.ts               이 도메인의 데이터 타입
       components/            화면 조각
  └─ shared/
       api/client.ts          실제 fetch가 일어나는 유일한 파일
       ui/                    Button·Card·Chip 등 공용 컴포넌트
       lib/                   formatCurrency 등 순수 함수
```

| 파일 | 하는 일 | 하지 않는 일 |
| --- | --- | --- |
| `pages/*.tsx` | hook 호출 → 값을 components에 전달 | state 선언, fetch, 비즈니스 로직 |
| `features/*/hooks.ts` | `useState`/`useEffect`로 state 관리, 사용자 액션 핸들러 정의 | 직접 `fetch()` 호출 |
| `features/*/api.ts` | `client.ts`의 `apiGet`/`apiPost`/... 로 엔드포인트 하나씩 함수화 | state 보관, JSX |
| `shared/api/client.ts` | 실제 `fetch()`, 인증 헤더, 응답 봉투(`{data,meta}`) 해제, 에러 변환 | 도메인 지식 |

**규칙: `fetch`를 직접 부르는 곳은 `client.ts` 하나뿐이다.** 컴포넌트가 hook을 거치지 않고 api.ts를 직접 부르지 않는다.

---

## 호출 체인

```
사용자/브라우저
   │ URL 접속
   ▼
router.tsx  ──match──▶  pages/<Screen>Page.tsx
   │                         │ const x = use<Domain>()
   │                         ▼
   │                    features/<domain>/hooks.ts
   │                         │ useState(초기값)
   │                         │ useEffect(() => { ... }, [])  ← 마운트 시 1회
   │                         ▼
   │                    features/<domain>/api.ts
   │                         │ apiGet(`/events/${id}/actions`)
   │                         ▼
   │                    shared/api/client.ts
   │                         │ fetch(BASE_URL + path)
   ▼                         ▼
                         BE 서버 (FastAPI)
                              │ { data: [...], meta: {...} }
   ┌──────────────────────────┘
   ▼
client.ts: body.data 만 꺼내 반환
   ▼
api.ts: 응답을 도메인 타입으로 매핑(필요 시)
   ▼
hooks.ts: setState(응답) → 렌더 트리거
   ▼
pages/*.tsx, components/*: 새 state로 다시 그려짐
```

state가 바뀌는 두 가지 경로:

| 경로 | 예시 | 특징 |
| --- | --- | --- |
| API 응답 | 마운트 시 목록 불러오기 | `useEffect` 안에서 `.then(setState)` |
| 사용자 액션 | 승인 버튼 클릭 | 핸들러가 `setState` 직접 호출. API 왕복 없이 즉시 반영 후, 필요하면 API 호출도 같이 |

---

## 예시 — M1 "승인 대기 목록"

파일: `fe/src/pages/M1DashboardPage.tsx`, `fe/src/features/dashboard/{hooks,api}.ts`, `fe/src/shared/api/client.ts`

**1. page — 조립만**

```tsx
// pages/M1DashboardPage.tsx
export default function M1DashboardPage() {
  const dashboard = useDashboard()
  return <ApprovalCarouselCard events={dashboard.events} onApprove={dashboard.handleApprove} ... />
}
```

**2. hook — state + 부수효과 + 핸들러**

```ts
// features/dashboard/hooks.ts
export function useDashboard() {
  const [events, setEvents] = useState(dashboardApi.getEventSummaries)  // 초기값: 목업

  useEffect(() => {
    dashboardApi.getPendingActionsFromApi(LIVE_EVENT_ID)   // 마운트 시 실제 API 시도
      .then((pendingActions) => setEvents(prev => /* 해당 행사만 교체 */))
      .catch(() => console.warn('API 실패, 목업 유지'))    // BE 없으면 조용히 실패
  }, [])

  function handleApprove(actionId: string) {
    removeAction(current.id, actionId)   // 사용자 액션 → state만 즉시 변경 (API 없음, 아직 BE 미구현)
  }

  return { events, handleApprove, ... }
}
```

**3. api — 엔드포인트 하나 = 함수 하나**

```ts
// features/dashboard/api.ts
export async function getPendingActionsFromApi(eventId: string): Promise<PendingAction[]> {
  const actions = await apiGet<ActionOutFromApi[]>(
    `/events/${eventId}/actions?status=PENDING&excludeType=CONFIRMATION`,
  )
  return actions.map((a) => ({ id: a.id, typeLabel: LABEL[a.type], title: a.title, subtitle: a.subtitle ?? '' }))
}
```

**4. client — 진짜 통신**

```ts
// shared/api/client.ts
export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path).then((body) => body.data)   // { data, meta } 봉투에서 data만 꺼냄
}
```

---

## BE 없는 화면은 어떻게 동작하나

`api.ts` 함수는 명세대로 이미 만들어져 있지만, BE 라우터가 없는 도메인은 **hook이 그 함수를 아예 호출하지 않고** 목업 함수를 대신 쓴다.

```ts
// features/records/hooks.ts
function mockState(): RecordsState {
  return { ...recordsApi.getRecordsMock(), details: recordsApi.getRecordDetailsMock() }
}
export function useRecords() {
  const [state, setState] = useState<RecordsState>(mockState)   // ← 실제 apiGetPage 대신 이걸 씀
  // ...
}
```

BE 엔드포인트가 생기면 **hook 안의 목업 호출 한 줄만 `recordsApi.getRecords(...)` 실제 호출로 바꾸면 된다.** page·components·api.ts는 안 건드린다.

| 도메인 | 상태 |
| --- | --- |
| `features/dashboard` (M1 승인 목록) | 실제 연동 |
| `features/events` (L2 확인요청/처리된 승인 조회) | 실제 연동 |
| `features/events` (승인·거절·완료 처리) | 목업 — #41 |
| `features/planning`, `features/records` | 전부 목업 — #41, #42 |

---

## 새 화면·기능을 추가할 때

1. `features/<domain>/types.ts`에 타입 정의
2. `api.ts`에 엔드포인트 함수 추가 (BE 없으면 같은 이름의 `xxxMock()` 함수도 같이)
3. `hooks.ts`에서 `useState` + `useEffect`로 그 함수를 불러 state 구성, 핸들러 작성
4. `components/`에 화면 조각 작성 (props로만 데이터 받음, 자체 fetch 금지)
5. `pages/<Screen>Page.tsx`에서 hook 불러 components 조립
6. `app/router.tsx`에 경로 등록
