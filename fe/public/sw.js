// Push 전용 최소 Service Worker. 인증 API와 회의 데이터를 오프라인 캐시하지 않는다.
self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

function sameOriginItemUrl(value) {
  const fallback = new URL('/meetings', self.location.origin).href
  if (typeof value !== 'string') return fallback
  try {
    const url = new URL(value, self.location.origin)
    if (
      url.origin !== self.location.origin ||
      !['https:', 'http:'].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return fallback
    return url.href
  } catch {
    return fallback
  }
}

self.addEventListener('push', (event) => {
  let payload = {}
  try {
    const parsed = event.data?.json()
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) payload = parsed
  } catch {
    // 잘못된 payload도 사용자에게 수신 사실을 표시하되 원문/인증 정보를 노출하지 않는다.
  }
  const title = typeof payload.title === 'string' ? payload.title.slice(0, 100) : '운영해 알림'
  const body =
    typeof payload.body === 'string' ? payload.body.slice(0, 300) : '예약한 항목을 확인해 주세요.'
  const itemData =
    payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
      ? payload.data
      : {}
  const id =
    typeof payload.notificationId === 'string'
      ? payload.notificationId.slice(0, 160)
      : typeof itemData.reminderId === 'string'
        ? itemData.reminderId.slice(0, 160)
        : undefined
  const tag = typeof payload.tag === 'string' ? payload.tag.slice(0, 160) : id
  const itemUrl = typeof itemData.url === 'string' ? itemData.url : payload.url
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/app-192.png',
      badge: '/icons/app-192.png',
      tag,
      data: {
        url: sameOriginItemUrl(itemUrl),
        notificationId: id,
        clubId: typeof itemData.clubId === 'string' ? itemData.clubId.slice(0, 160) : undefined,
        confirmedItemId:
          typeof itemData.confirmedItemId === 'string'
            ? itemData.confirmedItemId.slice(0, 160)
            : undefined,
        reminderId:
          typeof itemData.reminderId === 'string' ? itemData.reminderId.slice(0, 160) : undefined,
        source: 'server-push',
      },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  // 클릭 시에도 검사한다. 서버 payload를 외부 URL 탐색이나 javascript: 실행에 쓰지 않는다.
  const url = sameOriginItemUrl(event.notification.data?.url)
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const existing = windows.find((client) => new URL(client.url).origin === self.location.origin)
      if (existing) {
        const navigated = await existing.navigate(url)
        if (navigated) return navigated.focus()
      }
      return self.clients.openWindow(url)
    })(),
  )
})
