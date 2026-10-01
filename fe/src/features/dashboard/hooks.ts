// useDashboard 등 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as dashboardApi from '@/features/dashboard/api'
import type { PendingAction } from '@/features/dashboard/types'

// BE mock API(이슈 #30)가 고정 fixture로 응답하는 유일한 eventId.
// 실제 행사 조회가 생기면 이 상수 없이 현재 선택된 행사 id로 바로 호출한다.
const LIVE_EVENT_ID = 'evt_9f2c8a'
const pendingActionsKey = (eventId: string) => ['dashboard', 'pendingActions', eventId] as const

export function useDashboard() {
  const [mockEvents, setMockEvents] = useState(dashboardApi.getEventSummaries)
  const [index, setIndex] = useState(() => Math.min(1, mockEvents.length - 1))
  const queryClient = useQueryClient()

  const current = mockEvents[index]
  const isLiveEvent = current.id === LIVE_EVENT_ID
  const forecast = useMemo(() => dashboardApi.getBudgetForecast(current.id), [current.id])

  const pendingActionsQuery = useQuery({
    queryKey: pendingActionsKey(LIVE_EVENT_ID),
    queryFn: () => dashboardApi.getPendingActionsFromApi(LIVE_EVENT_ID),
    // BE mock은 승인·거절을 실제로 반영하지 않고 항상 같은 fixture를 돌려준다.
    // 기본값(포커스 복귀 시 자동 재요청)을 그대로 두면 방금 처리한 항목이 재요청 때마다
    // 되살아난다. 쓰기 API가 실제로 생기면 이 옵션을 지우고 기본 동작으로 되돌린다.
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  })

  // 목업 이벤트 2개는 애초에 API가 없어 원래 값 그대로 둔다.
  // 실제 연동된 행사는: 로딩 중엔 빈 배열(화면에서 로딩 표시), 실패하면 목업으로 폴백,
  // 성공하면 쿼리 결과로 덮는다.
  const events = mockEvents.map((event) => {
    if (event.id !== LIVE_EVENT_ID) return event
    if (pendingActionsQuery.isLoading) return { ...event, pendingActions: [] }
    if (pendingActionsQuery.data) return { ...event, pendingActions: pendingActionsQuery.data }
    return event
  })
  const currentPendingActions = events[index].pendingActions

  function goPrev() {
    setIndex((i) => (i - 1 + mockEvents.length) % mockEvents.length)
  }

  function goNext() {
    setIndex((i) => (i + 1) % mockEvents.length)
  }

  function removeFromMock(eventId: string, actionId: string) {
    setMockEvents((prev) =>
      prev.map((event) =>
        event.id === eventId
          ? { ...event, pendingActions: event.pendingActions.filter((action) => action.id !== actionId) }
          : event,
      ),
    )
  }

  function removeFromLiveCache(actionId: string) {
    queryClient.setQueryData<PendingAction[]>(pendingActionsKey(LIVE_EVENT_ID), (prev) =>
      prev?.filter((action) => action.id !== actionId),
    )
  }

  const approveMutation = useMutation({
    mutationFn: dashboardApi.approveAction,
    onSuccess: (_data, actionId) => removeFromLiveCache(actionId),
  })

  const denyMutation = useMutation({
    mutationFn: dashboardApi.denyAction,
    onSuccess: (_data, actionId) => removeFromLiveCache(actionId),
  })

  function handleApprove(actionId: string) {
    if (isLiveEvent) approveMutation.mutate(actionId)
    else removeFromMock(current.id, actionId)
  }

  function handleDeny(actionId: string) {
    if (isLiveEvent) denyMutation.mutate(actionId)
    else removeFromMock(current.id, actionId)
  }

  function handleApproveAll(eventId: string) {
    if (eventId === LIVE_EVENT_ID) {
      const ids = pendingActionsQuery.data?.map((action) => action.id) ?? []
      ids.forEach((id) => approveMutation.mutate(id))
    } else {
      setMockEvents((prev) => prev.map((event) => (event.id === eventId ? { ...event, pendingActions: [] } : event)))
    }
  }

  return {
    events,
    index,
    current: { ...current, pendingActions: currentPendingActions },
    forecast,
    goPrev,
    goNext,
    handleApprove,
    handleDeny,
    handleApproveAll,
    // 목업 이벤트에는 로딩·에러가 없어 실제 연동된 행사를 볼 때만 의미 있다.
    pendingActionsLoading: isLiveEvent && pendingActionsQuery.isLoading,
    pendingActionsError: isLiveEvent && pendingActionsQuery.isError,
  }
}
