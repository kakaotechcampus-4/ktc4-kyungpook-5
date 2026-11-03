let registrationPromise: Promise<ServiceWorkerRegistration | null> | undefined

export function supportsSystemNotifications(): boolean {
  return window.isSecureContext && 'serviceWorker' in navigator && 'Notification' in window
}

export function supportsWebPush(): boolean {
  return supportsSystemNotifications() && 'PushManager' in window
}

/** 앱 시작 시 호출해도 알림 권한을 요청하지 않는다. */
export function registerMeetingServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!supportsSystemNotifications()) return Promise.resolve(null)
  if (!registrationPromise) {
    registrationPromise = navigator.serviceWorker
      .register('/sw.js', { scope: '/' })
      .catch((error) => {
        registrationPromise = undefined
        throw error
      })
  }
  return registrationPromise
}

export async function getNotificationRegistration(): Promise<ServiceWorkerRegistration> {
  const registered = await registerMeetingServiceWorker()
  if (!registered) throw new Error('NOTIFICATIONS_UNSUPPORTED')
  if (registered.active) return registered

  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error('SERVICE_WORKER_TIMEOUT')), 10000)
    navigator.serviceWorker.ready.then(
      (registration) => {
        window.clearTimeout(timer)
        resolve(registration)
      },
      (error: unknown) => {
        window.clearTimeout(timer)
        reject(error)
      },
    )
  })
}

/** permission은 호출자의 명시적 클릭에서 먼저 획득한다. */
export async function showLocalNotificationCheck(): Promise<void> {
  if (!supportsSystemNotifications() || Notification.permission !== 'granted') {
    throw new Error('NOTIFICATION_PERMISSION_REQUIRED')
  }
  const registration = await getNotificationRegistration()
  await registration.showNotification('운영해 · 이 기기 알림 확인', {
    body: '로컬 시스템 알림입니다. 서버 Push 수신이나 예약 알림 완료를 뜻하지 않습니다.',
    icon: '/icons/app-192.png',
    tag: 'unyounghae-local-check',
    data: { url: new URL('/meetings', window.location.origin).href, source: 'local-check' },
  })
}

export function applicationServerKey(value: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const raw = window.atob((value + padding).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (character) => character.charCodeAt(0))
}
