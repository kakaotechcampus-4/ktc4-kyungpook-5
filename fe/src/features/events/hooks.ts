// useEvents... 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import * as eventsApi from '@/features/events/api'

// 아직 목업이라 동기로 끝난다. `GET /events`가 생기면 로딩·에러 상태가 여기에 붙는다.
export function useEventList() {
  return eventsApi.getEventList()
}
