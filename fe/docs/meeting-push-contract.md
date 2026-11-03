# 회의 베타 PWA·Web Push 연결

2026-10-19. FE 기준 develop `0f97b2b`, 신규 BE Push 계약을 반영한 구현이다. 서버 API가 없는 환경의 404 또는 설정 오류는 실패로 표시한다. 로컬 시스템 알림, Push 서비스의 발송 접수, 실제 기기 표시, 서버 예약 완료를 구분한다.

## FE 연결 위치

- `main.tsx`에서 `registerMeetingServiceWorker()`를 호출한다. 등록은 권한을 요청하지 않는다.
- `NotificationsPanel`은 사용자 클릭에서만 알림 권한을 요청한다. 로그인 계정이 바뀌면 컴포넌트를 다시 마운트한다(`key={me.id}`).
- `features/notifications/hooks.ts` → `api.ts` → `shared/api/client.ts`로 요청한다. 다른 feature를 import하지 않는다.
- `public/sw.js`는 Push를 시스템 알림으로 표시한다. payload URL은 수신 및 클릭 시 두 번 검증하며 HTTP(S)의 같은 origin만 열고 잘못된 URL은 `/meetings`로 이동한다.
- 실제 예약 payload의 `data.url`을 우선 사용하고 `tag`를 알림 식별 태그로 유지한다. `data.clubId/confirmedItemId/reminderId`도 알림 클릭 데이터에 보존한다. 기존 top-level `url/notificationId`는 호환 입력으로 지원한다.
- 최소 manifest 및 192/512px 아이콘을 제공한다. 인증·회의 API나 파일을 오프라인 캐시하지 않는다.

## BE와 맞춘 API

모든 경로 앞에는 `/api/v1`이 붙는다. 기존 `Authorization: Bearer …`와 `{ data, meta }` 봉투를 사용한다. userId는 브라우저가 지정하지 않고 서버가 세션에서 결정한다.

| 요청 | data 예시 / 의미 |
|---|---|
| `GET /push/vapid-public-key` | `{ "publicKey": "base64url-public-key" }`. 비밀 키를 FE에 보내지 않는다. |
| `POST /push/subscriptions` | 입력은 `PushSubscription.toJSON()`의 `{ endpoint, expirationTime, keys: { p256dh, auth } }`. 응답 `{ "id": "…", "active": true, … }`. |
| `DELETE /push/subscriptions/{id}` | 응답 `{ "id": "…", "deleted": true }`. 구독 소유권은 서버가 검사한다. |
| `POST /push/test` | 입력 `{ "subscriptionId": "…" }`로 현재 기기만 지정. 응답 `{ "status": "SERVICE_ACCEPTED", "acceptedCount": 1, "failedCount": 0, "invalidatedCount": 0, "failures": [] }`. |

테스트 status는 `SERVICE_ACCEPTED / PARTIAL_FAILURE / FAILED`. 접수 건수가 있어도 기기 도착을 확정하지 않는다. 브라우저 구독이 이미 있다는 이유로 서버 등록 완료를 추정하지 않는다. 서버 등록 실패 시 사용자가 다시 등록할 수 있도록 실패를 표시한다.

## 서버 Push payload 예시

```json
{
  "type": "TASK_REMINDER",
  "title": "회의에서 확인한 할 일",
  "body": "자료 제출 시간을 확인해 주세요.",
  "tag": "reminder:reminder-ULID",
  "url": "/meetings?taskId=item-ULID&clubId=club-ULID",
  "data": {
    "url": "/meetings?taskId=item-ULID&clubId=club-ULID",
    "clubId": "club-ULID",
    "confirmedItemId": "item-ULID",
    "reminderId": "reminder-ULID"
  }
}
```

알림 본문은 지정 수신자 기기의 잠금 화면에도 표시될 수 있으므로 서버에서 필요한 문구만 보낸다. 서버는 클라이언트가 준 수신자·권한·예약 시각을 검사하며, 후보 ACCEPTED와 알림 예약/발송을 따로 관리한다. FE는 일정·예약 화면에서 별도로 생성/변경/취소한다. SW는 예약 타이머를 실행하지 않는다.

## 작은 실제 확인 순서

1. HTTPS 또는 localhost의 Chrome에서 실제 계정으로 로그인한다. Application 패널에서 manifest와 `/sw.js` 활성화를 확인한다.
2. 회의 화면의 `알림 허용`을 직접 누른다. `이 기기에서 알림 확인`은 서버가 없는 상태에서도 시스템 알림을 표시하는 로컬 검사다.
3. VAPID 설정을 갖춘 BE에 `이 기기 Push 등록`을 요청한다. 실패를 로컬 성공으로 대체하지 않는다.
4. `서버 테스트 Push`를 눌러 서비스 접수 응답과 실제 OS 알림을 각각 확인한다. 알림을 누르면 회의/항목이 열린다.
5. 내용·시간·담당자·수신자를 확인해 가까운 미래의 알림을 서버에 예약한다. 화면을 닫고 실제 시스템 알림 한 건을 받아 예약 흐름을 확인한다.

FE 코드만으로 4~5번 성공을 주장할 수 없다. 실제 VAPID·서버 예약 실행기·기기 권한을 함께 사용해 확인한 결과를 STATUS에 기록한다.

`node --test tests/*.test.mjs`로 실제 `public/sw.js`의 nested payload, 알림 태그, 같은 origin URL 수신/클릭 검증과 malformed fallback 회귀 테스트를 실행한다. 이 Node 검사는 실제 기기 Push 수신 검사를 대체하지 않는다.

브라우저 API 근거: [PushManager.subscribe](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe), [ServiceWorkerRegistration.showNotification](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/showNotification).
