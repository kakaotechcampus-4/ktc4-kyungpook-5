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

// ── 2단계(흐름 만들기) ──
// 단계는 13개 고정 목록에서 고른 것만 나온다. 묶음도 셋으로 고정이다.
export type StepPhase = '사전 준비' | '모집 · 확정' | '행사 진행 · 마무리'
// 누가 하는지. 점 색으로 구분한다.
export type StepActor = 'AI 실행' | '승인 필요' | '직접 수행'

export interface PlanStep {
  id: string
  phase: StepPhase
  name: string
  actor: StepActor
  // 이 단계에 붙는 Action 유형(공지 · 수금 등). 없으면 비운다.
  actionLabel?: string
  date: string
  desc: string
}

// 오른쪽 요약. 일곱 줄로 고정이라 계획이 바뀌어도 자리가 흔들리지 않는다.
export interface PlanSummary {
  totalSteps: number
  aiSteps: number
  approvalSteps: number
  manualSteps: number
  collect: string
  notice: string
  period: string
}

// 시작하기 전에 짚어줄 것. 일정이 비었거나 단계가 겹칠 때만 생긴다.
export interface PlanWarning {
  title: string
  body: string
  actionLabel: string
}
