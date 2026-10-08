// M1 메인 훅. 화면은 반드시 이 훅을 거쳐 데이터에 접근한다.
import { DEMO_JUDGEMENTS } from '@/features/dashboard/mock'
import type { ToriJudgement } from '@/features/dashboard/types'
import { useDemo } from '@/features/events/hooks'

// TODO(연동): 토리의 판단은 API 명세가 없다. 생기면 useQuery로 바꾼다. 지금은 ?demo일 때만 예시를 준다.
export function useToriJudgement(eventId: string | undefined): ToriJudgement | undefined {
  const demo = useDemo()
  return demo && eventId ? DEMO_JUDGEMENTS[eventId] : undefined
}
