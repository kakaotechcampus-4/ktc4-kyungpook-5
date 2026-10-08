// 계획 1단계(큰 틀 잡기) 도메인 타입.

export interface ChatMessage {
  id: string
  from: '토리' | '나'
  text: string
  // 토리가 묻고 바로 고를 수 있게 주는 답. 마지막 말풍선에만 남는다.
  quickReplies?: string[]
}

// 큰 틀에서 정해야 하는 것. 여섯 개로 고정이라 화면이 흔들리지 않는다.
export const PLAN_FACT_KEYS = ['행사 이름', '종류', '예상 인원', '참가비', '일정', '장소'] as const
export type PlanFactKey = (typeof PLAN_FACT_KEYS)[number]

// 아직 안 정한 항목은 값을 비운다. note는 「후보 2곳」처럼 반쯤 정해진 경우에 쓴다.
export type PlanFacts = Partial<Record<PlanFactKey, { value: string; decided: boolean }>>
