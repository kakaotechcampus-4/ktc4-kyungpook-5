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

// ponytail: 첫 페이지 100건만 받는다. 한 동아리 행사가 100건을 넘으면 페이지 넘김을 붙인다.
export function getEvents(clubId: string, status?: EventStatus) {
  const query = new URLSearchParams({ clubId, size: '100' })
  if (status) query.set('status', status)
  return apiGet<EventSummary[]>(`/events?${query}`)
}

// BE에는 있다. useEventDetail에는 아직 붙이지 않았다.
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
