import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ApiError } from '@/shared/api/types'
import {
  applicationServerKey,
  getNotificationRegistration,
  showLocalNotificationCheck,
  supportsSystemNotifications,
  supportsWebPush,
} from '@/shared/pwa/register'
import type { PushServerAdapter } from './api'

function permissionState(): NotificationPermission | 'unsupported' {
  return supportsSystemNotifications() ? Notification.permission : 'unsupported'
}

export function notificationErrorMessage(error: unknown): string {
  if (error instanceof Error && 'response' in error) {
    const response = error.response
    if (
      response &&
      typeof response === 'object' &&
      'status' in response &&
      response.status === 404
    ) {
      return '서버가 아직 Push API를 제공하지 않아요. 이 기기 알림 확인은 사용할 수 있어요.'
    }
  }
  if (
    error instanceof ApiError &&
    ['UNAUTHORIZED', 'AUTH_REQUIRED', 'TOKEN_EXPIRED'].includes(error.code)
  ) {
    return '다시 로그인한 뒤 알림을 연결해 주세요.'
  }
  if (
    error instanceof ApiError &&
    ['PUSH_NOT_CONFIGURED', 'PUSH_UNAVAILABLE', 'NOT_FOUND'].includes(error.code)
  ) {
    return '서버 Push API 또는 발송 설정이 아직 준비되지 않았어요. 이 기기 알림 확인은 사용할 수 있어요.'
  }
  if (error instanceof ApiError && error.code === 'PUSH_SUBSCRIPTION_CONFLICT') {
    return '이 브라우저의 구독이 다른 계정에 연결되어 있어요. 이전 계정에서 구독을 해제한 뒤 다시 등록해 주세요.'
  }
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return '브라우저에서 알림을 허용한 뒤 다시 시도해 주세요.'
  }
  if (error instanceof Error && error.message === 'PUSH_DISABLED') {
    return '서버가 아직 Push 발송을 준비 중이에요.'
  }
  return '알림 작업을 완료하지 못했어요. 브라우저 설정과 서버 연결을 확인해 주세요.'
}

export function useSystemNotifications(server: PushServerAdapter | undefined) {
  const [permission, setPermission] = useState(permissionState)
  const [localBusy, setLocalBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [localError, setLocalError] = useState<unknown>(null)
  // 브라우저 구독 존재만으로 현재 로그인 계정의 서버 등록 완료를 추정하지 않는다.
  const [subscriptionId, setSubscriptionId] = useState<string | null>(null)

  useEffect(() => {
    const refresh = () => setPermission(permissionState())
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [])

  const configuration = useQuery({
    queryKey: ['push', 'configuration'],
    queryFn: () => {
      if (!server) throw new Error('PUSH_NOT_CONNECTED')
      return server.getConfiguration()
    },
    enabled: !!server,
    retry: false,
  })

  const subscribe = useMutation({
    mutationFn: async () => {
      if (!server || !configuration.data?.publicKey) throw new Error('PUSH_DISABLED')
      if (!supportsWebPush() || Notification.permission !== 'granted')
        throw new Error('NOTIFICATION_PERMISSION_REQUIRED')
      const registration = await getNotificationRegistration()
      const existing = await registration.pushManager.getSubscription()
      const subscription =
        existing ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: applicationServerKey(configuration.data.publicKey),
        }))
      // 서버 실패 시 브라우저 구독은 남을 수 있다. 서버 등록 성공 상태로 표시하지 않는다.
      const result = await server.registerSubscription(subscription.toJSON())
      if (!result.id || !result.active) throw new Error('PUSH_REGISTRATION_FAILED')
      return result
    },
    onSuccess: (result) => {
      setSubscriptionId(result.id)
      setNotice('이 기기의 구독을 서버에 등록했어요. 실제 수신은 테스트 Push로 확인해 주세요.')
    },
  })

  const unsubscribe = useMutation({
    mutationFn: async () => {
      if (!server || !subscriptionId) throw new Error('PUSH_NOT_CONNECTED')
      const registration = await getNotificationRegistration()
      const subscription = await registration.pushManager.getSubscription()
      const result = await server.removeSubscription(subscriptionId)
      if (!result.deleted) throw new Error('SERVER_UNSUBSCRIBE_FAILED')
      if (subscription) {
        // 서버의 해제를 먼저 확인한다. 실패하면 해제 완료로 표시하지 않는다.
        const removed = await subscription.unsubscribe()
        if (!removed) throw new Error('BROWSER_UNSUBSCRIBE_FAILED')
      }
    },
    onSuccess: () => {
      setSubscriptionId(null)
      setNotice('이 기기의 Push 구독을 해제했어요. 이미 생성된 일정과 예약은 별도로 확인해 주세요.')
    },
  })

  const testPush = useMutation({
    mutationFn: async () => {
      if (!server || !subscriptionId) throw new Error('PUSH_NOT_CONNECTED')
      const result = await server.sendTestPush(subscriptionId)
      if (result.status === 'FAILED' || result.acceptedCount < 1)
        throw new Error('PUSH_NOT_ACCEPTED')
      return result
    },
    onSuccess: (result) =>
      setNotice(
        `Push 서비스가 ${result.acceptedCount}건을 접수했어요.${result.failedCount ? ` ${result.failedCount}건은 실패했어요.` : ''} 이 기기의 시스템 알림을 직접 확인해 주세요.`,
      ),
  })

  function clearFeedback() {
    setLocalError(null)
    setNotice('')
    subscribe.reset()
    unsubscribe.reset()
    testPush.reset()
  }

  async function requestPermission() {
    if (!supportsSystemNotifications()) return
    setLocalBusy(true)
    clearFeedback()
    try {
      // 사용자 버튼 클릭에서 바로 호출한다. 마운트나 로그인 성공 시 자동 요청하지 않는다.
      const next = await Notification.requestPermission()
      setPermission(next)
      setNotice(
        next === 'granted'
          ? '알림을 허용했어요. 이 기기의 시스템 알림을 확인할 수 있어요.'
          : '알림이 허용되지 않았어요. 브라우저 사이트 설정에서 변경할 수 있어요.',
      )
    } catch (error) {
      setLocalError(error)
    } finally {
      setLocalBusy(false)
    }
  }

  async function checkLocally() {
    setLocalBusy(true)
    clearFeedback()
    try {
      await showLocalNotificationCheck()
      setNotice(
        '이 기기의 시스템 알림 표시를 요청했어요. 서버 Push와 예약 발송은 별도로 확인해야 해요.',
      )
    } catch (error) {
      setLocalError(error)
    } finally {
      setLocalBusy(false)
    }
  }

  return {
    permission,
    webPushSupported: supportsWebPush(),
    configuration,
    registered: !!subscriptionId,
    notice,
    error:
      localError ?? subscribe.error ?? unsubscribe.error ?? testPush.error ?? configuration.error,
    busy: localBusy || subscribe.isPending || unsubscribe.isPending || testPush.isPending,
    requestPermission,
    checkLocally,
    subscribe: () => {
      clearFeedback()
      subscribe.mutate()
    },
    unsubscribe: () => {
      clearFeedback()
      unsubscribe.mutate()
    },
    testPush: () => {
      clearFeedback()
      testPush.mutate()
    },
    retryServer: () => {
      clearFeedback()
      void configuration.refetch()
    },
  }
}
