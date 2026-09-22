// 도메인 타입 정의 — FE API 명세 §1 행사 계획(P1·P2) 응답 모양을 그대로 따른다.
//
// StepActor·ActionType 같은 공용 enum은 features/events/types.ts에도 같은 값이 있다.
// feature끼리 서로 import하지 않는 이 저장소 규칙을 따라 여기에도 적는다(records도 같다).
export type StepPhase = 'PREPARATION' | 'RECRUITING' | 'EXECUTION'
export type StepActor = 'AI' | 'APPROVAL_REQUIRED' | 'MANUAL'
export type MessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM'
export type DraftStage = 'CHAT' | 'FLOW'
export type EventType = 'MT' | 'WELCOME' | 'PICNIC' | 'ACADEMIC' | 'WORKSHOP' | 'ETC'

export type ActionType =
  'EXTERNAL_SEND' | 'TRANSFER' | 'EXPENSE' | 'CONTRACT' | 'NOTICE' | 'CONFIRMATION'

// ── 1단계 (P1) ──

// GET /events/drafts — 우측 "임시 저장한 계획" 카드
export interface EventDraftItem {
  id: string
  title: string
  // Step이 0개면 CHAT, 1개 이상이면 FLOW. DB 컬럼이 아니라 서버 계산값이다.
  stage: DraftStage
  savedAt: string
  conversationId: string
}

export interface PlanMessage {
  id: string
  role: MessageRole
  content: string
  createdAt: string
}

// 우측 "지금까지 정해진 것" 복원용. 명세 POST /conversations/{id}/messages 응답의 collected다.
export interface PlanCollected {
  eventType: EventType | null
  startDate: string | null
  endDate: string | null
  headcount: number | null
  budgetTotal: number | null
  locationCandidates: string[] | null
}

// GET /conversations/{conversationId}/messages
export interface PlanConversation {
  conversationId: string
  eventId: string
  messages: PlanMessage[]
  collected: PlanCollected
  readyToGenerate: boolean
}

// POST /conversations/{conversationId}/messages
export interface PlanChatResult {
  message: PlanMessage
  collected: PlanCollected
  readyToGenerate: boolean
}

// POST /events
export interface PlanDraftCreated {
  id: string
  title: string
  status: 'PLANNING'
  conversationId: string
  messages: PlanMessage[]
}

// 말풍선 안의 유형 칩과 "작년 기록" 카드는 명세 message에 자리가 없다(content 한 줄뿐).
// 화면에만 있는 값이라 서버로 보내는 PlanMessage와 따로 둔다.
export interface PlanChatTurn extends PlanMessage {
  quickReplies?: EventType[]
  reference?: { title: string; rows: Array<[label: string, value: string]> }
}

// ── 2단계 (P2) ── GET /events/{eventId}/plan

export interface PlanAction {
  id: string
  type: ActionType
  title: string
  subtitle: string | null
  // irreversible은 사실, approveNeeded는 그 사실에 대한 정책 판정이다(명세).
  irreversible: boolean
  approveNeeded: boolean
  amount: number | null
}

export interface PlanStep {
  id: string
  stepOrder: number
  phase: StepPhase
  name: string
  actor: StepActor
  startedTime: string | null
  deadline: string | null
  actions: PlanAction[]
}

export interface PlanPhaseGroup {
  phase: StepPhase
  name: string
  description: string
  steps: PlanStep[]
}

export interface PlanSummary {
  totalSteps: number
  countByActor: Partial<Record<StepActor, number>>
  collectionPlan: { times: number; feePerPerson: number } | null
  noticeCount: number
  periodStart: string
  periodEnd: string
}

// RULE은 code로 문구를 조립하고, AI는 자유 문장을 그대로 쓴다(명세 v1 변경).
export interface PlanWarning {
  source: 'RULE' | 'AI'
  code?: string
  params?: Record<string, string | number>
  suggestion?: string
  // FE가 모르는 code일 때 대신 쓰는 폴백 문구다.
  debugMessage?: string
  message?: string
}

export interface ExcludedStep {
  name: string
  reason: string
}

export interface EventPlan {
  eventId: string
  title: string
  phases: PlanPhaseGroup[]
  summary: PlanSummary
  warnings: PlanWarning[]
  excludedSteps: ExcludedStep[]
}

// PATCH /events/{eventId}/steps/{stepId} 로 보내는 값
export interface StepPatch {
  name?: string
  startedTime?: string | null
  deadline?: string | null
}
