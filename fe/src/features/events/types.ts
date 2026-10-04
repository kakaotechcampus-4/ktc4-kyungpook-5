// 행사 도메인 타입. 이름·값은 FE API 명세(docs/week6/fe/운영해_FE_API_명세_v1.md)를 따른다.

// 단계 상태. DB 컬럼이 아니라 서버가 계산해 내려준다.
export type StepState = 'DONE' | 'CURRENT' | 'TODO'

export type EventStatus = 'PLANNING' | 'ON_GOING' | 'COMPLETE'

// GET /events 목록 한 줄
export interface EventSummary {
  id: string
  title: string
  status: EventStatus
  startDate: string | null
  endDate: string | null
  dday: number | null
  currentStepName: string | null
  stepProgress: Array<{ stepOrder: number; state: StepState }>
  pendingApprovalCount: number
  // TODO: 아래 둘은 GET /events 응답에 아직 없다. 카드에 필요해 BE에 추가를 요청한다.
  location: string | null
  headcount: number | null
}
