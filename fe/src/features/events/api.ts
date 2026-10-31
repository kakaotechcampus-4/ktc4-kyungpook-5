// 행사 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiGetPage, apiPost } from '@/shared/api/client'
import type {
  ActionPage,
  StepComplete,
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

// ── 쓰기 ──────────────────────────────────────────────────────────────────
// 넷 다 조회에서 받은 version을 expectedVersion으로 돌려보낸다. 그사이 내용이
// 바뀌었으면 서버가 409 VERSION_CONFLICT로 거절한다.
// 행사가 운영 중(ON_GOING)일 때만 받는다 — 계획 중에는 거절된다.

export function approveAction(actionId: string, expectedVersion: number) {
  return apiPost<EventAction>(`/actions/${encodeURIComponent(actionId)}/approve`, {
    expectedVersion,
  })
}

export function denyAction(actionId: string, expectedVersion: number, reason?: string) {
  return apiPost<EventAction>(`/actions/${encodeURIComponent(actionId)}/deny`, {
    expectedVersion,
    reason: reason || null,
  })
}

// 확인 요청(CONFIRMATION) 전용. choice는 options[].key, 직접 처리면 'MANUAL'이다.
export function resolveAction(
  actionId: string,
  expectedVersion: number,
  choice: string,
  manualValue?: string,
) {
  return apiPost<EventAction>(`/actions/${encodeURIComponent(actionId)}/resolve`, {
    expectedVersion,
    choice,
    manualValue: manualValue || null,
  })
}

// 운영진이 직접 보내거나 이체한 뒤의 기록. 앱이 대신 실행하지는 않는다.
export function markActionDone(actionId: string, expectedVersion: number) {
  return apiPost<EventAction>(`/actions/${encodeURIComponent(actionId)}/done`, {
    expectedVersion,
  })
}

export function completeStep(stepId: string) {
  return apiPost<StepComplete>(`/steps/${encodeURIComponent(stepId)}/complete`)
}
