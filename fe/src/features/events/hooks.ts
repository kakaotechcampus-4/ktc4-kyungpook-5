// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// ?demo는 명시적인 시연 예시이며, 그 외에는 실제 서버를 조회한다.
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/shared/auth/store'
import {
  getEventActions,
  getEventActionPage,
  getEventDetail,
  getEventSteps,
  getEvents,
} from './api'
import {
  DEMO_ACTIONS,
  DEMO_CONFIRMATIONS,
  DEMO_EVENT_DETAILS,
  DEMO_EVENTS,
  DEMO_RESOLVED,
  DEMO_STEP_ACTIONS,
  DEMO_STEPS,
} from '@/features/events/mock'
import type {
  ActionPage,
  EventAction,
  EventDetail,
  EventStatus,
  EventStep,
  EventSummary,
} from '@/features/events/types'

export function useDemo() {
  return useSearchParams()[0].has('demo')
}

export function useEvents(status?: EventStatus) {
  const demo = useDemo()
  const clubId = useAuthStore((state) => state.clubId)
  const userId = useAuthStore((state) => state.me?.id)
  return useQuery({
    queryKey: ['events', userId, clubId, status, demo],
    queryFn: async (): Promise<EventSummary[]> =>
      demo
        ? DEMO_EVENTS.filter((e) => !status || e.status === status)
        : await getEvents(clubId!, status),
    enabled: demo || Boolean(clubId),
    retry: false,
  })
}

// 없는 행사면 null(초기 화면)
export function useEventDetail(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'detail', demo],
    queryFn: async (): Promise<EventDetail | null> =>
      demo ? (DEMO_EVENT_DETAILS[eventId!] ?? null) : await getEventDetail(eventId!),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

export function useEventSteps(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'steps', demo],
    queryFn: async (): Promise<EventStep[]> =>
      demo ? (DEMO_STEPS[eventId!] ?? []) : await getEventSteps(eventId!),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

// M1 승인 대기. 확인 요청은 L2에서 따로 보인다.
export function usePendingApprovals(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'actions', 'pendingApprovals', demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? (DEMO_ACTIONS[eventId!] ?? [])
        : await getEventActions(eventId!, 'status=PENDING&excludeType=CONFIRMATION'),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

// L2 확인 요청
export function useConfirmations(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'actions', 'confirmations', demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? (DEMO_CONFIRMATIONS[eventId!] ?? [])
        : await getEventActions(eventId!, 'status=PENDING&type=CONFIRMATION'),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

const NO_ACTIONS: ActionPage = { items: [], totalCount: 0 }

// L2 처리된 승인: 최근 몇 건 + 전체 개수
export function useResolvedActions(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'actions', 'resolved', demo],
    queryFn: async (): Promise<ActionPage> =>
      demo
        ? (DEMO_RESOLVED[eventId!] ?? NO_ACTIONS)
        : getEventActionPage(eventId!, 'status=APPROVED,DONE,DENIED&size=3'),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

// Step 모달: 한 단계의 Action 전부
export function useStepActions(eventId: string | undefined, stepId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'actions', 'step', stepId, demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? (DEMO_STEP_ACTIONS[eventId!]?.[stepId!] ?? [])
        : (await getEventActions(eventId!, 'size=100')).filter(
            (action) => action.stepId === stepId,
          ),
    enabled: !!eventId && !!stepId && (demo || Boolean(userId && clubId)),
  })
}
