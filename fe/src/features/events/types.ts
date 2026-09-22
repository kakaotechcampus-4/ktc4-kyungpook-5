// 도메인 타입 정의 — FE API 명세 §2 `GET /events` 응답 모양을 그대로 따른다.
export type EventStatus = 'PLANNING' | 'ON_GOING' | 'COMPLETE'

export type StepState = 'DONE' | 'CURRENT' | 'TODO'

export interface StepProgress {
  stepOrder: number
  state: StepState
}

// 🔸 명세에서 스키마 확정 대기 중인 필드. `GET /events`와 `GET /events/{id}`가 같은 모양으로 준다.
export interface PaymentSummary {
  paidCount: number
  totalCount: number
  collected: number
  target: number
}

export interface BudgetSummary {
  spent: number
  planned: number
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
  payment: PaymentSummary | null
  budget: BudgetSummary | null
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

// ── L2 행사 상세 ── FE API 명세 §3 응답 모양을 그대로 따른다.
export type StepActor = 'AI' | 'APPROVAL_REQUIRED' | 'MANUAL'

export type ActionType =
  'EXTERNAL_SEND' | 'TRANSFER' | 'EXPENSE' | 'CONTRACT' | 'NOTICE' | 'CONFIRMATION'

export type ActionStatus = 'PENDING' | 'APPROVED' | 'DENIED' | 'DONE' | 'FAILED'

export type MemberRole = 'OWNER' | 'MANAGER' | 'MEMBER'

// GET /events/{eventId}
export interface EventDetail {
  id: string
  title: string
  status: EventStatus
  startDate: string | null
  endDate: string | null
  dday: number | null
  // 🔸 location·headcount는 명세에서 저장 위치가 미정인 필드다.
  location: string | null
  headcount: number | null
  currentStep: { id: string; stepOrder: number; name: string } | null
  payment: PaymentSummary | null
  budget: BudgetSummary | null
}

// GET /events/{eventId}/steps
export interface StepAction {
  id: string
  title: string
  status: ActionStatus
  approveNeeded: boolean
}

export interface EventStep {
  id: string
  stepOrder: number
  name: string
  actor: StepActor
  state: StepState
  startedTime: string | null
  deadline: string | null
  doneActions: StepAction[]
  remainingActions: StepAction[]
}

// GET /events/{eventId}/actions
export interface ActionMember {
  id: string
  name: string
  role: MemberRole
}

export interface ActionOption {
  key: string
  label: string
}

export interface EventAction {
  id: string
  type: ActionType
  title: string
  subtitle: string | null
  status: ActionStatus
  dueDate: string | null
  resolvedAt: string | null
  resolvedBy: ActionMember | null
  denyReason: string | null
  // CONFIRMATION 전용. 다른 타입은 항상 null이다.
  options: ActionOption[] | null
  allowManual: boolean | null
}

// 🔸 GET /events/{id}/budget · /payments 는 명세에서 아직 ⏸ 보류다. 합계(spent·collected 등)는
// GET /events/{id} 의 budget·payment 에 있고, 여기서는 그 위에 덧붙는 것만 온다.
export interface PaymentIssue {
  id: string
  kind: 'UNPAID' | 'REFUND'
  name: string
  note: string
  statusLabel: string
}
