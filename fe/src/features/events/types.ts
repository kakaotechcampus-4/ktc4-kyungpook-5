// 행사 도메인 타입. 이름·값은 FE API 명세(docs/week6/fe/운영해_FE_API_명세_v1.md)를 따른다.

// DB 컬럼이 아니라 서버가 계산해 내려준다.
export type StepState = 'DONE' | 'CURRENT' | 'TODO'

// 취소 두 값은 취소 정리(L2-d)를 거치는 동안과 끝난 뒤를 나눈다.
export type EventStatus = 'PLANNING' | 'ON_GOING' | 'COMPLETE' | 'CANCELLING' | 'CANCELLED'

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
}

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
  startsAt?: string | null
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
  // 승인·거절·확인 응답·완료 요청에 그대로 돌려보낸다. 본 적 없는 내용을
  // 처리하지 않기 위해서다. 그사이 바뀌었으면 서버가 409로 거절한다.
  version: number
  type: ActionType
  title: string
  subtitle: string | null
  dueDate: string | null
  status: ActionStatus
  // 단계에 안 묶인 확인 요청은 null
  stepId?: string | null
  resolvedAt?: string | null
  resolvedBy?: { id: string; name: string; role: MemberRole } | null
  denyReason?: string | null
  // 확인 요청(CONFIRMATION) 전용
  options?: Array<{ key: string; label: string }> | null
  allowManual?: boolean | null
  // TODO: 아래 셋은 명세에 없다. Step 모달 Action 카드에서만 쓴다.
  // content: 승인 전엔 토리가 준비한 초안, 승인 뒤엔 확정 문구, 확인 요청은 질문
  content?: string | null
  answer?: string | null
  failReason?: string | null
}

// 목록 일부와 전체 개수("12건")
export interface ActionPage {
  items: EventAction[]
  totalCount: number
}

// ── 행사 취소 정리 ──
// 네 가지로 고정이다. 앱이 대신 취소해주지 않고, 운영진이 직접 처리한 뒤 완료로 표시한다.
export type CancelTaskState = 'DONE' | 'CURRENT' | 'TODO'

export interface CancelTask {
  id: string
  name: string
  // 무엇을 하면 되는지 한 줄. 끝난 뒤에는 누가 언제 했는지로 바뀐다.
  desc: string
  state: CancelTaskState
  date?: string
  // 연락 문구가 필요한 일(참가자 안내 · 업체 연락)에만 있다.
  message?: string
  // 진행 중인 일의 남은 할 일. 토리가 짚어준다.
  todos?: string[]
  note?: string
}

// POST /steps/{id}/complete 결과. 행동이 모두 끝나 자동 완료된 단계는 completedBy가 null이다.
export interface StepComplete {
  id: string
  completedAt: string
  completedBy: { id: string; name: string; role: MemberRole } | null
  // 끝나지 않은 행동 수. 남아 있어도 완료는 되고, 화면이 그 사실을 알린다.
  pendingActionCount: number
}
