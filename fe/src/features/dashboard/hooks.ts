// useDashboard 등 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useMemo, useState } from 'react'
import * as dashboardApi from '@/features/dashboard/api'

export function useDashboard() {
  const [events, setEvents] = useState(dashboardApi.getEventSummaries)
  const [index, setIndex] = useState(() => Math.min(1, events.length - 1))

  const current = events[index]
  const forecast = useMemo(() => dashboardApi.getBudgetForecast(current.id), [current.id])

  function goPrev() {
    setIndex((i) => (i - 1 + events.length) % events.length)
  }

  function goNext() {
    setIndex((i) => (i + 1) % events.length)
  }

  function removeAction(eventId: string, actionId: string) {
    setEvents((prev) =>
      prev.map((event) =>
        event.id === eventId
          ? { ...event, pendingActions: event.pendingActions.filter((action) => action.id !== actionId) }
          : event,
      ),
    )
  }

  function handleApprove(actionId: string) {
    removeAction(current.id, actionId)
  }

  function handleDeny(actionId: string) {
    removeAction(current.id, actionId)
  }

  function handleApproveAll(eventId: string) {
    setEvents((prev) => prev.map((event) => (event.id === eventId ? { ...event, pendingActions: [] } : event)))
  }

  return {
    events,
    index,
    current,
    forecast,
    goPrev,
    goNext,
    handleApprove,
    handleDeny,
    handleApproveAll,
  }
}
