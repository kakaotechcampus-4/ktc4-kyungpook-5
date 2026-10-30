// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// 주소에 ?demo가 있으면 시연용 예시(mock.ts)를 준다. 목록만 서버에 붙였고, 나머지는 아직 빈 값을 준다.
// TODO(연동): 각 queryFn을 주석에 적힌 eventsApi 호출로 바꾼다. 화면은 고치지 않아도 된다.
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { getEvents } from '@/features/events/api'
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
import { useAuthStore } from '@/shared/auth/store'

export function useDemo() {
  return useSearchParams()[0].has('demo')
}

// 소속 없이 둘러보는 중이면 부를 동아리가 없어 빈 목록을 준다.
export function useEvents(status?: EventStatus) {
  const demo = useDemo()
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', 'list', clubId, status, demo],
    queryFn: async (): Promise<EventSummary[]> => {
      if (demo) return DEMO_EVENTS.filter((e) => !status || e.status === status)
      return clubId ? getEvents(clubId, status) : []
    },
  })
}

// 없는 행사면 null(초기 화면)
// TODO(연동): eventsApi.getEventDetail(eventId)
export function useEventDetail(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'detail', demo],
    queryFn: async (): Promise<EventDetail | null> =>
      demo ? (DEMO_EVENT_DETAILS[eventId!] ?? null) : null,
    enabled: !!eventId,
  })
}

// TODO(연동): eventsApi.getEventSteps(eventId)
export function useEventSteps(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'steps', demo],
    queryFn: async (): Promise<EventStep[]> => (demo ? (DEMO_STEPS[eventId!] ?? []) : []),
    enabled: !!eventId,
  })
}

// M1 승인 대기. 확인 요청은 L2에서 따로 보인다.
// TODO(연동): eventsApi.getEventActions(eventId, 'status=PENDING&excludeType=CONFIRMATION')
export function usePendingApprovals(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'pendingApprovals', demo],
    queryFn: async (): Promise<EventAction[]> => (demo ? (DEMO_ACTIONS[eventId!] ?? []) : []),
    enabled: !!eventId,
  })
}

// L2 확인 요청
// TODO(연동): eventsApi.getEventActions(eventId, 'status=PENDING&type=CONFIRMATION')
export function useConfirmations(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'confirmations', demo],
    queryFn: async (): Promise<EventAction[]> => (demo ? (DEMO_CONFIRMATIONS[eventId!] ?? []) : []),
    enabled: !!eventId,
  })
}

const NO_ACTIONS: ActionPage = { items: [], totalCount: 0 }

// L2 처리된 승인: 최근 몇 건 + 전체 개수
// TODO(연동): eventsApi.getEventActionPage(eventId, 'status=APPROVED,DONE,DENIED&size=3')
export function useResolvedActions(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'resolved', demo],
    queryFn: async (): Promise<ActionPage> =>
      demo ? (DEMO_RESOLVED[eventId!] ?? NO_ACTIONS) : NO_ACTIONS,
    enabled: !!eventId,
  })
}

// Step 모달: 한 단계의 Action 전부
// TODO(연동): 단계 조건이 명세에 없어 eventsApi.getEventActions(eventId, 'size=100')로 받아 stepId로 거른다.
// 기본은 20건이라 size를 붙인다(최대 100). 넘는 행사가 생기면 BE에 stepId 조건을 요청한다.
export function useStepActions(eventId: string | undefined, stepId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'step', stepId, demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo ? (DEMO_STEP_ACTIONS[eventId!]?.[stepId!] ?? []) : [],
    enabled: !!eventId && !!stepId,
  })
}
