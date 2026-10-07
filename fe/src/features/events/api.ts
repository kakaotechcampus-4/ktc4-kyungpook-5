// 행사 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiGetPage } from '@/shared/api/client'
import type {
  ActionPage,
  EventAction,
  EventDetail,
  EventStatus,
  EventStep,
  EventSummary,
} from '@/features/events/types'

export function getEvents(status?: EventStatus) {
  return apiGet<EventSummary[]>(`/events${status ? `?status=${status}` : ''}`)
}

// BE에 아직 없다(명세에만 있음)
export function getEventDetail(eventId: string) {
  return apiGet<EventDetail>(`/events/${eventId}`)
}

export function getEventSteps(eventId: string) {
  return apiGet<EventStep[]>(`/events/${eventId}/steps`)
}

// query 예: 'status=PENDING&excludeType=CONFIRMATION'
export function getEventActions(eventId: string, query: string) {
  return apiGet<EventAction[]>(`/events/${eventId}/actions?${query}`)
}

// 목록과 전체 개수를 함께 받는다. 예: 'status=APPROVED,DONE,DENIED&size=3'
export async function getEventActionPage(eventId: string, query: string): Promise<ActionPage> {
  const res = await apiGetPage<EventAction>(`/events/${eventId}/actions?${query}`)
  return { items: res.data, totalCount: res.meta?.totalCount ?? res.data.length }
}
