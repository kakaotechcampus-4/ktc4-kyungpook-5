// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// 지금은 서버 연동 전이라 주소에 ?demo가 있으면 시연용 예시(mock.ts)를, 없으면 빈 값을 준다.
// TODO(연동): 각 queryFn을 주석에 적힌 eventsApi 호출로 바꾼다. 화면은 고치지 않아도 된다.
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
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

// TODO(연동): eventsApi.getEvents(status)
export function useEvents(status?: EventStatus) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', status, demo],
    queryFn: async (): Promise<EventSummary[]> =>
      demo ? DEMO_EVENTS.filter((e) => !status || e.status === status) : [],
  })
}

// L2 상단 카드. 없는 행사면 null(초기 화면).
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

// M1 승인 대기: 결정이 필요한 Action만. 확인 요청(CONFIRMATION)은 L2에서 따로 보인다.
// TODO(연동): eventsApi.getEventActions(eventId, 'status=PENDING&excludeType=CONFIRMATION')
export function usePendingApprovals(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'pendingApprovals', demo],
    queryFn: async (): Promise<EventAction[]> => (demo ? (DEMO_ACTIONS[eventId!] ?? []) : []),
    enabled: !!eventId,
  })
}

// L2 확인 요청: 토리가 혼자 정하기 어려워 묻는 일
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

// L2 처리된 승인: 최근 몇 건만 보이고 개수는 전체를 센다
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

// Step 모달: 한 단계의 Action 전부(할 일 · 처리된 일)
// TODO(연동): 명세에 단계로 거르는 조건이 없다. eventsApi.getEventActions(eventId, '')로 받아 stepId로 거른다.
export function useStepActions(eventId: string | undefined, stepId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'step', stepId, demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo ? (DEMO_STEP_ACTIONS[eventId!]?.[stepId!] ?? []) : [],
    enabled: !!eventId && !!stepId,
  })
}
