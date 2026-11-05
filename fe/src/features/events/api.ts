// 행사 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiGetPage, apiPost } from '@/shared/api/client'
import type {
  ActionPage,
  EventAction,
  EventDetail,
  EventStatus,
  EventStep,
  EventSummary,
} from '@/features/events/types'

// 목록 필터와 건수는 전체 결과를 기준으로 한다.
async function getAllPages<T>(path: string, params: URLSearchParams): Promise<T[]> {
  const items: T[] = []
  let page = 1
  while (true) {
    params.set('page', String(page))
    params.set('size', '100')
    const result = await apiGetPage<T>(`${path}?${params}`)
    items.push(...result.data)
    if (!result.meta || items.length >= result.meta.totalCount || result.data.length === 0) break
    page += 1
  }
  return items
}

export function getEvents(clubId: string, status?: EventStatus) {
  const params = new URLSearchParams({ clubId })
  if (status) params.set('status', status)
  return getAllPages<EventSummary>('/events', params)
}

export function getEventDetail(eventId: string) {
  return apiGet<EventDetail>(`/events/${encodeURIComponent(eventId)}`)
}

export function getEventSteps(eventId: string) {
  return apiGet<EventStep[]>(`/events/${encodeURIComponent(eventId)}/steps`)
}

// query 예: 'status=PENDING&excludeType=CONFIRMATION'
export function getEventActions(eventId: string, query: string) {
  return getAllPages<EventAction>(
    `/events/${encodeURIComponent(eventId)}/actions`,
    new URLSearchParams(query),
  )
}

// 목록과 전체 개수를 함께 받는다. 예: 'status=APPROVED,DONE,DENIED&size=3'
export async function getEventActionPage(eventId: string, query: string): Promise<ActionPage> {
  const res = await apiGetPage<EventAction>(
    `/events/${encodeURIComponent(eventId)}/actions?${query}`,
  )
  return { items: res.data, totalCount: res.meta?.totalCount ?? res.data.length }
}

export const completeEvent = (eventId: string) =>
  apiPost<{ id: string; status: EventStatus; title: string; startDate: string | null }>(`/events/${encodeURIComponent(eventId)}/complete`)
export const beginEventCancellation = (eventId: string) =>
  apiPost<{ id: string; status: EventStatus; title: string; startDate: string | null }>(`/events/${encodeURIComponent(eventId)}/cancel`)
export const getCancelTasks = (eventId: string) =>
  apiGet<{ id: string; taskOrder: number; name: string; description: string; message: string | null; state: 'DONE' | 'CURRENT' | 'TODO'; completedAt: string | null }[]>(`/events/${encodeURIComponent(eventId)}/cancel/tasks`)
export const completeCancelTask = (eventId: string, taskId: string) =>
  apiPost(`/events/${encodeURIComponent(eventId)}/cancel/tasks/${encodeURIComponent(taskId)}/complete`)
export const completeStep = (stepId: string) =>
  apiPost<{ id: string; completedAt: string; completedBy: unknown; pendingActionCount: number }>(`/steps/${encodeURIComponent(stepId)}/complete`)
function actionVersion(action: EventAction): number {
  if (action.version == null) throw new Error('행동 정보를 다시 불러온 뒤 처리해 주세요.')
  return action.version
}
export const resolveAction = (action: EventAction, choice: string, manualValue?: string) =>
  apiPost<EventAction>(`/actions/${encodeURIComponent(action.id)}/resolve`, { expectedVersion: actionVersion(action), choice, manualValue })
export const approveAction = (action: EventAction) =>
  apiPost<EventAction>(`/actions/${encodeURIComponent(action.id)}/approve`, { expectedVersion: actionVersion(action) })
export const denyAction = (action: EventAction, reason: string) =>
  apiPost<EventAction>(`/actions/${encodeURIComponent(action.id)}/deny`, { expectedVersion: actionVersion(action), reason })
export const markActionDone = (action: EventAction) =>
  apiPost<EventAction>(`/actions/${encodeURIComponent(action.id)}/done`, { expectedVersion: actionVersion(action) })
