// useEvents... 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useEffect, useState } from 'react'
import * as eventsApi from '@/features/events/api'

// 아직 목업이라 동기로 끝난다. `GET /events`가 생기면 로딩·에러 상태가 여기에 붙는다.
export function useEventList() {
  return eventsApi.getEventList()
}

// L2 행사 상세. 확인 요청·처리된 승인만 API에서 오고 나머지는 아직 목업이다.
export function useEventDetail(eventId: string) {
  const [actions, setActions] = useState(eventsApi.getEventActions)

  useEffect(() => {
    let cancelled = false

    eventsApi
      .getEventActionsFromApi(eventId)
      .then((result) => {
        if (!cancelled) setActions(result)
      })
      .catch((error: unknown) => {
        // mock API가 아직 안 떠 있을 수 있다. 이때는 기존 목업 데이터를 그대로 보여준다.
        console.warn('[events] 승인 목록을 API에서 불러오지 못해 목업 데이터를 유지합니다.', error)
      })

    return () => {
      cancelled = true
    }
  }, [eventId])

  // TODO: POST /actions/{actionId}/resolve 에 { choice } 로 보낸다. 엔드포인트가 아직 없어
  // 지금은 화면에서만 지운다.
  function resolveConfirmation(actionId: string, choice: string) {
    console.info('[events] 확인 요청 처리', actionId, choice)
    setActions((prev) => ({
      ...prev,
      confirmations: prev.confirmations.filter((action) => action.id !== actionId),
    }))
  }

  return {
    event: eventsApi.getEventDetail(),
    steps: eventsApi.getEventSteps(),
    budgetNote: eventsApi.getBudgetNote(),
    paymentIssues: eventsApi.getPaymentIssues(),
    ...actions,
    resolveConfirmation,
  }
}
