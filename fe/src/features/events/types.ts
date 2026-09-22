// 도메인 타입 정의 — FE API 명세 §2 `GET /events` 응답 모양을 그대로 따른다.
export type EventStatus = 'PLANNING' | 'ON_GOING' | 'COMPLETE'

export type StepState = 'DONE' | 'CURRENT' | 'TODO'

export interface StepProgress {
  stepOrder: number
  state: StepState
}

export interface EventListItem {
  id: string
  title: string
  status: EventStatus
  startDate: string | null
  endDate: string | null
  dday: number | null
  currentStepName: string | null
  stepProgress: StepProgress[]
  pendingApprovalCount: number
  // 🔸 명세에서 스키마 확정 대기 중인 필드. 자리만 잡아둔다.
  payment: { paidCount: number; totalCount: number; collected: number; target: number } | null
  budget: { spent: number; planned: number } | null
}

// GET /events/drafts — L1 "계획 중" 카드에 필요한 것만 추린 모양.
export interface EventDraft {
  id: string
  title: string
  stageLabel: string
}

export interface EventListView {
  ongoing: EventListItem[]
  drafts: EventDraft[]
  completedCount: number
}
