// useDashboard 등 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useEffect, useMemo, useState } from 'react'
import * as dashboardApi from '@/features/dashboard/api'

// BE mock API(이슈 #30)가 고정 fixture로 응답하는 유일한 eventId.
// 실제 행사 조회가 생기면 이 상수 없이 현재 선택된 행사 id로 바로 호출한다.
const LIVE_EVENT_ID = 'evt_9f2c8a'

export function useDashboard() {
  const [events, setEvents] = useState(dashboardApi.getEventSummaries)
  const [index, setIndex] = useState(() => Math.min(1, events.length - 1))

  const current = events[index]
  const forecast = useMemo(() => dashboardApi.getBudgetForecast(current.id), [current.id])

  useEffect(() => {
    let cancelled = false

    dashboardApi
      .getPendingActionsFromApi(LIVE_EVENT_ID)
      .then((pendingActions) => {
        if (cancelled) return
        setEvents((prev) =>
          prev.map((event) => (event.id === LIVE_EVENT_ID ? { ...event, pendingActions } : event)),
        )
      })
      .catch((error: unknown) => {
        // mock API가 아직 안 떠 있을 수 있다. 이때는 기존 목업 데이터를 그대로 보여준다.
        console.warn('[dashboard] 승인 대기 목록을 API에서 불러오지 못해 목업 데이터를 유지합니다.', error)
      })

    return () => {
      cancelled = true
    }
  }, [])

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
