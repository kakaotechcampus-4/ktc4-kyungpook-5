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
  // TODO: 아래 둘은 GET /events 응답에 아직 없다. DB에는 location · expected_headcount로 있으니
  // 응답에 실어 달라고 BE에 요청하거나, 결정에 따라 카드에서 뺀다.
  location: string | null
  headcount: number | null
}

// GET /events/{id} — L2 상단 카드
export interface EventDetail {
  id: string
  title: string
  status: EventStatus
  startDate: string | null
  endDate: string | null
  dday: number | null
  location: string | null
  headcount: number | null
  currentStep: { id: string; stepOrder: number; name: string } | null
  // TODO: 명세에 없다. 담당자("박수겸 · 총무")를 응답에 실어 달라고 BE에 요청하거나, 결정에 따라 뺀다.
  manager: string | null
}

// 단계를 누가 진행하는지
export type StepActor = 'AI' | 'APPROVAL_REQUIRED' | 'MANUAL'

// GET /events/{id}/steps 한 줄
// 선택(?) 필드는 응답에는 늘 오지만, 예시 데이터는 진행 중인 단계에만 채운다.
export interface EventStep {
  id: string
  stepOrder: number
  name: string
  state: StepState
  deadline: string | null
  actor?: StepActor
  startedTime?: string | null
  // L2 현재 단계 카드의 "이 단계에서 한 일" · "남은 일"
  doneActions?: Array<{ id: string; title: string; status: ActionStatus }>
  remainingActions?: Array<{
    id: string
    title: string
    status: ActionStatus
    approveNeeded: boolean
  }>
}

export type ActionType =
  'EXTERNAL_SEND' | 'TRANSFER' | 'EXPENSE' | 'CONTRACT' | 'NOTICE' | 'CONFIRMATION'

export type ActionStatus = 'PENDING' | 'APPROVED' | 'DENIED' | 'DONE' | 'FAILED'

export type MemberRole = 'OWNER' | 'MANAGER' | 'MEMBER'

// GET /events/{id}/actions 한 줄
// 선택(?) 필드는 응답에는 늘 오지만, 예시 데이터는 그 화면에서 쓰는 것만 채운다.
export interface EventAction {
  id: string
  type: ActionType
  title: string
  subtitle: string | null
  dueDate: string | null
  status?: ActionStatus
  resolvedAt?: string | null
  resolvedBy?: { id: string; name: string; role: MemberRole } | null
  // 확인 요청(CONFIRMATION) 전용. 버튼 하나가 선택지 하나다.
  options?: Array<{ key: string; label: string }> | null
  allowManual?: boolean | null
}

// 목록 일부와 전체 개수("12건"). 처리된 승인처럼 최근 몇 건만 보일 때 쓴다.
export interface ActionPage {
  items: EventAction[]
  totalCount: number
}
