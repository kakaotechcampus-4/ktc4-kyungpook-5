// 행사 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet } from '@/shared/api/client'
import type { EventAction, EventStatus, EventStep, EventSummary } from '@/features/events/types'

export function getEvents(status?: EventStatus) {
  return apiGet<EventSummary[]>(`/events${status ? `?status=${status}` : ''}`)
}

export function getEventSteps(eventId: string) {
  return apiGet<EventStep[]>(`/events/${eventId}/steps`)
}

// query 예: 'status=PENDING&excludeType=CONFIRMATION'
export function getEventActions(eventId: string, query: string) {
  return apiGet<EventAction[]>(`/events/${eventId}/actions?${query}`)
}
