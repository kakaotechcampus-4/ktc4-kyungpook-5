// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// 주소에 ?demo가 있으면 시연용 예시(mock.ts)를 준다. 그 분기는 시연용이라 남겨 둔다.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  approveAction,
  completeEvent,
  completeStep,
  denyAction,
  getEventActionPage,
  getEventActions,
  getEventDetail,
  getEventSteps,
  getEvents,
  markActionDone,
  resolveAction,
} from '@/features/events/api'
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
import { ApiError } from '@/shared/api/types'
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
export function useEventDetail(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'detail', demo],
    queryFn: async (): Promise<EventDetail | null> =>
      demo ? (DEMO_EVENT_DETAILS[eventId!] ?? null) : getEventDetail(eventId!),
    enabled: !!eventId,
  })
}

export function useEventSteps(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'steps', demo],
    queryFn: async (): Promise<EventStep[]> =>
      demo ? (DEMO_STEPS[eventId!] ?? []) : getEventSteps(eventId!),
    enabled: !!eventId,
  })
}

// M1 승인 대기. 확인 요청은 L2에서 따로 보인다.
export function usePendingApprovals(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'pendingApprovals', demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? (DEMO_ACTIONS[eventId!] ?? [])
        : getEventActions(eventId!, 'status=PENDING&excludeType=CONFIRMATION'),
    enabled: !!eventId,
  })
}

// L2 확인 요청
export function useConfirmations(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'confirmations', demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? (DEMO_CONFIRMATIONS[eventId!] ?? [])
        : getEventActions(eventId!, 'status=PENDING&type=CONFIRMATION'),
    enabled: !!eventId,
  })
}

const NO_ACTIONS: ActionPage = { items: [], totalCount: 0 }

// L2 처리된 승인: 최근 몇 건 + 전체 개수
export function useResolvedActions(eventId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'resolved', demo],
    queryFn: async (): Promise<ActionPage> =>
      demo
        ? (DEMO_RESOLVED[eventId!] ?? NO_ACTIONS)
        : getEventActionPage(eventId!, 'status=APPROVED,DONE,DENIED&size=3'),
    enabled: !!eventId,
  })
}

// Step 모달: 한 단계의 Action 전부
// 단계로 거르는 조건이 서버에 없어 전부 받아 stepId로 거른다. 기본 20건이라 size를
// 최대(100)로 올린다. 넘는 행사가 생기면 BE에 stepId 조건을 요청한다.
export function useStepActions(eventId: string | undefined, stepId: string | undefined) {
  const demo = useDemo()
  return useQuery({
    queryKey: ['events', eventId, 'actions', 'step', stepId, demo],
    queryFn: async (): Promise<EventAction[]> => {
      if (demo) return DEMO_STEP_ACTIONS[eventId!]?.[stepId!] ?? []
      const all = await getEventActions(eventId!, 'size=100')
      return all.filter((action) => action.stepId === stepId)
    },
    enabled: !!eventId && !!stepId,
  })
}

// ── 쓰기 ──────────────────────────────────────────────────────────────────
// 처리하면 목록·단계·상세가 모두 달라진다. 이 행사 밑을 통째로 다시 받는다.
function useEventMutation<TArgs, TResult>(
  eventId: string | undefined,
  run: (args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: run,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['events', eventId] }),
  })
}

export function useApproveAction(eventId: string | undefined) {
  return useEventMutation(eventId, (action: EventAction) =>
    approveAction(action.id, action.version),
  )
}

export function useDenyAction(eventId: string | undefined) {
  return useEventMutation(eventId, ({ action, reason }: { action: EventAction; reason: string }) =>
    denyAction(action.id, action.version, reason),
  )
}

export function useResolveAction(eventId: string | undefined) {
  return useEventMutation(
    eventId,
    ({
      action,
      choice,
      manualValue,
    }: {
      action: EventAction
      choice: string
      manualValue?: string
    }) => resolveAction(action.id, action.version, choice, manualValue),
  )
}

export function useMarkActionDone(eventId: string | undefined) {
  return useEventMutation(eventId, (action: EventAction) =>
    markActionDone(action.id, action.version),
  )
}

export function useCompleteEvent(eventId: string | undefined) {
  return useEventMutation(eventId, () => completeEvent(eventId!))
}

export function useCompleteStep(eventId: string | undefined) {
  return useEventMutation(eventId, (step: EventStep) => completeStep(step.id))
}

// 처리 실패 문구. 무엇이 막았는지 사용자가 다음에 할 일로 바꿔 보여준다.
export function actionErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'VERSION_CONFLICT')
      return '내용이 그사이 바뀌었어요. 새로고침한 뒤 다시 봐주세요.'
    if (cause.code === 'ALREADY_RESOLVED') return '이미 처리된 건이에요.'
    if (cause.code === 'EVENT_NOT_OPERATING') return '운영 중인 행사에서만 처리할 수 있어요.'
    if (cause.code === 'FORBIDDEN') return '처리할 권한이 없어요. 회장·임원만 할 수 있어요.'
    return (Object.values(cause.fields ?? {})[0] ?? cause.message) || '처리하지 못했어요.'
  }
  return '처리하지 못했어요. 연결 상태를 확인해 주세요.'
}
