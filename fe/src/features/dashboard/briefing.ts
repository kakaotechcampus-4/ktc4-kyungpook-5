// 메인 첫 화면의 브리핑과 토리 답을 서버에서 받는다.
import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/features/dashboard/api'
import type { BriefingState, ToriDeskReply } from '@/features/dashboard/desk'
import { toDeskReply } from '@/features/dashboard/desk'
import type { components } from '@/shared/api/schema'

type ClarificationContext = components['schemas']['ToriClarificationContext']

export function useBriefing(clubId: string, userId: string): BriefingState {
  const query = useQuery({
    queryKey: ['tori-briefing', userId, clubId],
    queryFn: () => dashboardApi.briefing(clubId),
    retry: false,
  })
  if (query.data) return { status: 'ready', data: query.data }
  if (query.isError) return { status: 'error', retry: () => void query.refetch() }
  return { status: 'loading' }
}

export async function respondFromServer(
  clubId: string,
  message: string,
  clarification: ClarificationContext | null,
): Promise<ToriDeskReply> {
  const result = await dashboardApi.message(clubId, {
    message,
    ...(clarification ? { clarificationContext: clarification } : {}),
  })
  return toDeskReply(result)
}

// 첫 화면의 질문 예시. 지금 데이터로 답이 나오는 것만 고른다(서버의 되묻기 예시와 같은 기준).
export function liveStarters(briefing: BriefingState): string[] {
  const starters: string[] = []
  if (briefing.status === 'ready') {
    const ongoing = briefing.data.events.find((event) => event.status === 'ON_GOING')
    if (ongoing) starters.push(`${ongoing.title} 어디까지 됐어?`)
    if (briefing.data.items.some((item) => item.kind === 'approval'))
      starters.push('승인 기다리는 거 보여줘')
  }
  starters.push('지난 회의에서 정한 할 일', '이번 주 내 할 일')
  return starters.slice(0, 4)
}
