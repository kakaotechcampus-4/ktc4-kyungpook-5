// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// 주소에 ?demo가 있으면 서버 대신 시연용 예시(mock.ts)를 돌려준다. 화면은 둘을 구분하지 않는다.
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import * as eventsApi from '@/features/events/api'
import { DEMO_ACTIONS, DEMO_EVENTS, DEMO_STEPS } from '@/features/events/mock'
import type { EventStatus } from '@/features/events/types'

export function useDemo() {
  return useSearchParams()[0].has('demo')
}

export function useEvents(status?: EventStatus) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', status, demo],
    queryFn: async () =>
      demo
        ? DEMO_EVENTS.filter((e) => !status || e.status === status)
        : eventsApi.getEvents(status),
  })
}

export function useEventSteps(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'steps', demo],
    queryFn: async () => (demo ? (DEMO_STEPS[eventId!] ?? []) : eventsApi.getEventSteps(eventId!)),
    enabled: !!eventId,
  })
}

// M1 승인 대기: 결정이 필요한 Action만. 확인 요청(CONFIRMATION)은 L2에서 따로 보인다.
export function usePendingApprovals(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'pendingApprovals', demo],
    queryFn: async () =>
      demo
        ? (DEMO_ACTIONS[eventId!] ?? [])
        : eventsApi.getEventActions(eventId!, 'status=PENDING&excludeType=CONFIRMATION'),
    enabled: !!eventId,
  })
}
