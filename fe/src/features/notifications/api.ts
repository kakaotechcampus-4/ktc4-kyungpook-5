import { apiDelete, apiGet, apiPost } from '@/shared/api/client'

export interface PushConfiguration {
  publicKey: string
}

export interface RegisteredPushSubscription {
  id: string
  active: boolean
}

export interface PushDispatchResult {
  status: 'SERVICE_ACCEPTED' | 'PARTIAL_FAILURE' | 'FAILED'
  acceptedCount: number
  failedCount: number
  invalidatedCount: number
  failures: { subscriptionId: string; code: string }[]
}

export interface PushServerAdapter {
  getConfiguration(): Promise<PushConfiguration>
  registerSubscription(subscription: PushSubscriptionJSON): Promise<RegisteredPushSubscription>
  removeSubscription(id: string): Promise<{ id: string; deleted: boolean }>
  sendTestPush(subscriptionId: string): Promise<PushDispatchResult>
}

export interface PushApiPaths {
  configuration: string
  subscriptions: string
  testPush: string
}

/**
 * BE가 경로와 아래 DTO를 확인했을 때만 생성해 화면에 주입한다.
 * 미구현 경로에 요청하거나 API 실패를 fixture 성공으로 바꾸지 않는다.
 * 서버가 로그인 계정과 구독 소유권을 판단한다.
 */
export function createPushServerAdapter(paths: PushApiPaths): PushServerAdapter {
  return {
    getConfiguration: () => apiGet<PushConfiguration>(paths.configuration),
    registerSubscription: (subscription) =>
      apiPost<RegisteredPushSubscription>(paths.subscriptions, subscription),
    removeSubscription: (id) =>
      apiDelete<{ id: string; deleted: boolean }>(
        `${paths.subscriptions}/${encodeURIComponent(id)}`,
      ),
    sendTestPush: (subscriptionId) =>
      apiPost<PushDispatchResult>(paths.testPush, { subscriptionId }),
  }
}

// 2026-10-19 BE와 맞춘 신규 계약. 서버가 준비되지 않았으면 실패 상태를 그대로 표시한다.
export const notificationServer = createPushServerAdapter({
  configuration: '/push/vapid-public-key',
  subscriptions: '/push/subscriptions',
  testPush: '/push/test',
})
