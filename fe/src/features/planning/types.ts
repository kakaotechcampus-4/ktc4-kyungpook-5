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

// 항목 하나의 상태. AI가 내려주는 값을 화면 네 가지로 옮긴 것이다(app/ai/contracts.py).
//   확정   condition_meta[field].status === 'specified'
//   잠정   condition_meta[field].status === 'tentative' — 근거가 된 발화를 함께 보인다
//   미정   조건 값이 null
//   나중에 deferred_topics에 그 주제가 들어 있다
// 「확정」도 행사 최종 승인은 아니다. 사용자가 그렇게 말했다는 뜻이다.
export type PlanFactStatus = '확정' | '잠정' | '미정' | '나중에'

export interface PlanFact {
  status: PlanFactStatus
  // 미정·나중에면 비운다. 참가비 0원은 '무료'로 적어 미정과 구분한다.
  value?: string
  // 잠정일 때의 근거 발화(condition_meta[field].evidence.quote)
  quote?: string
}

export type PlanFacts = Partial<Record<PlanFactKey, PlanFact>>

// 생성 가능 여부를 막는 사유(generation_readiness.reasons). 서버가 정한다.
export type GenerationBlockReason = 'event_type_missing' | 'condition_change_pending'

export interface GenerationReadiness {
  canGenerate: boolean
  reasons: GenerationBlockReason[]
}

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
// 계산은 서버가 한다(AI는 "세면 나오는 값"이라 담지 않는다 — contracts.py PlanDraft).
// 서버가 조립한 문장이 아니라 값으로 받아 문구는 화면에서 만든다.
export interface PlanSummary {
  totalSteps: number
  aiSteps: number
  approvalSteps: number
  manualSteps: number
  // 수금 Action의 횟수와 1인당 금액. 수금 단계가 없으면 null.
  // 모두 같은 금액을 낸다는 전제다 — 감면·면제·차등은 이 한 줄로 표현되지 않는다(#177).
  collection: { times: number; feePerPerson: number } | null
  // 공지 Action의 횟수. 개별 연락은 세지 않는다.
  noticeCount: number
  // 준비 기간(첫 단계 시작일 → 마지막 단계 마감일). 행사 당일 기간이 아니다(#177).
  periodStart: string | null
  periodEnd: string | null
}

// 시작하기 전에 짚어줄 것. 일정이 비었거나 단계가 겹칠 때만 생긴다.
export interface PlanWarning {
  title: string
  body: string
  actionLabel: string
}
