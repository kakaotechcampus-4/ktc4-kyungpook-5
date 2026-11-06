// 행사 서버 상태 훅. 화면은 반드시 이 훅을 거쳐 서버 데이터에 접근한다.
// ?demo는 명시적인 시연 예시이며, 그 외에는 실제 서버를 조회한다.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/shared/auth/store'
import {
  getEventActions,
  getEventActionPage,
  getEventDetail,
  getEventSteps,
  getEvents,
  approveAction,
  completeStep,
  completeEvent,
  denyAction,
  markActionDone,
  resolveAction,
  getCancelTasks,
  completeCancelTask,
  beginEventCancellation,
  requestActionDraft,
  updateActionContent,
} from './api'
import { draftPollInterval } from '@/features/events/actionDraft'
import {
  DEMO_EVENT_DETAILS,
  DEMO_EVENTS,
  DEMO_RESOLVED,
  DEMO_STEPS,
  demoRequestDraft,
  demoSaveContent,
  demoStepActions,
  demoTodoActions,
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

export function useEvents(status?: EventStatus, enabled = true) {
  const demo = useDemo()
  const clubId = useAuthStore((state) => state.clubId)
  const userId = useAuthStore((state) => state.me?.id)
  return useQuery({
    queryKey: ['events', userId, clubId, status, demo],
    queryFn: async (): Promise<EventSummary[]> =>
      demo
        ? DEMO_EVENTS.filter((e) => !status || e.status === status)
        : await getEvents(clubId!, status),
    enabled: enabled && (demo || Boolean(clubId)),
    retry: false,
  })
}

const eventDetailKey = (
  userId: string | undefined,
  clubId: string | null,
  eventId: string | undefined,
  demo: boolean,
) => ['events', userId, clubId, eventId, 'detail', demo]

// 첫 계획의 주소로 이동하기 전에 상세 조회도 같은 캐시에 준비한다.
export function usePrefetchEventDetail() {
  const client = useQueryClient()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return (eventId: string) =>
    client.fetchQuery({
      queryKey: eventDetailKey(userId, clubId, eventId, false),
      queryFn: () => getEventDetail(eventId),
      retry: false,
    })
}

// 없는 행사면 null(초기 화면)
export function useEventDetail(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: eventDetailKey(userId, clubId, eventId, demo),
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

// L2 지금 할 일: 승인 대기 · 실행 대기 · 실패 · 토리 질문을 한 번에 받는다.
// 어떤 일을 어떤 순서로 보일지는 todo.ts가 정한다.
export function useTodoActions(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'actions', 'todo', demo],
    queryFn: async (): Promise<EventAction[]> =>
      demo
        ? demoTodoActions(eventId!)
        : await getEventActions(eventId!, 'status=PENDING,APPROVED,FAILED&size=100'),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
    // 토리가 초안을 쓰는 동안만 몇 초마다 다시 조회한다(#335)
    refetchInterval: (query) => draftPollInterval(query.state.data),
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
        : getEventActionPage(eventId!, 'status=APPROVED,DONE,DENIED&excludeType=CONFIRMATION&size=3'),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

export function useCancelTasks(eventId: string | undefined) {
  const demo = useDemo()
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'cancelTasks', demo],
    queryFn: () => (demo ? [] : getCancelTasks(eventId!)),
    enabled: !!eventId && (demo || Boolean(userId && clubId)),
  })
}

export function useBeginCancellation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (eventId: string) => beginEventCancellation(eventId),
    onSuccess: (_data, eventId) => {
      void client.invalidateQueries({ queryKey: ['events'] })
      void client.invalidateQueries({ queryKey: ['events', undefined, undefined, eventId, 'cancelTasks'] })
    },
  })
}

export function useCompleteCancelTask() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, taskId }: { eventId: string; taskId: string }) => completeCancelTask(eventId, taskId),
    onSuccess: (_data, variables) => {
      void client.invalidateQueries({ queryKey: ['events'] })
      void client.invalidateQueries({ queryKey: ['events', undefined, undefined, variables.eventId, 'cancelTasks'] })
    },
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
        ? demoStepActions(eventId!, stepId!)
        : (await getEventActions(eventId!, 'size=100')).filter(
            (action) => action.stepId === stepId,
          ),
    enabled: !!eventId && !!stepId && (demo || Boolean(userId && clubId)),
    refetchInterval: (query) => draftPollInterval(query.state.data),
  })
}

export function useCompleteStep() {
  const client = useQueryClient()
  return useMutation({ mutationFn: completeStep, onSuccess: () => client.invalidateQueries({ queryKey: ['events'] }) })
}
export function useCompleteEvent() {
  const client = useQueryClient()
  return useMutation({ mutationFn: completeEvent, onSuccess: () => client.invalidateQueries({ queryKey: ['events'] }) })
}
export function useResolveAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ action, choice, manualValue }: { action: EventAction; choice: string; manualValue?: string }) => resolveAction(action, choice, manualValue),
    onSuccess: () => client.invalidateQueries({ queryKey: ['events'] }),
  })
}
export function useApproveAction() {
  const client = useQueryClient()
  // 409(그사이 초안 도착 등)에도 다시 불러와야 최신 내용을 보고 승인할 수 있다
  return useMutation({ mutationFn: approveAction, onSettled: () => client.invalidateQueries({ queryKey: ['events'] }) })
}
export function useDenyAction() {
  const client = useQueryClient()
  return useMutation({ mutationFn: ({ action, reason }: { action: EventAction; reason: string }) => denyAction(action, reason), onSuccess: () => client.invalidateQueries({ queryKey: ['events'] }) })
}
export function useMarkActionDone() {
  const client = useQueryClient()
  return useMutation({ mutationFn: markActionDone, onSuccess: () => client.invalidateQueries({ queryKey: ['events'] }) })
}

// 토리 초안 다시 받기(#335). 성공·409 모두 다시 불러와 최신 상태를 보인다.
export function useRequestActionDraft() {
  const demo = useDemo()
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (action: EventAction) =>
      demo ? demoRequestDraft(action) : await requestActionDraft(action),
    onSettled: () => client.invalidateQueries({ queryKey: ['events'] }),
  })
}

// 본문 고치기(#335). 응답은 단계 모양이라 버리고, 다시 불러온 Action을 쓴다.
// onSettled가 다시 불러오기를 기다리므로 mutateAsync가 끝나면 목록은 이미 최신이다.
export function useUpdateActionContent() {
  const demo = useDemo()
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({ action, content, expectedVersion }: { action: EventAction; content: string; expectedVersion: number | undefined }) => {
      if (demo) return demoSaveContent(action.id, content, expectedVersion)
      await updateActionContent(action, content, expectedVersion ?? action.version)
    },
    onSettled: () => client.invalidateQueries({ queryKey: ['events'] }),
  })
}
