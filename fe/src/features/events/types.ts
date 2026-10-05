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

// GET /events/{id}/steps 한 줄 (M1 스테퍼에 쓰는 필드만)
export interface EventStep {
  id: string
  stepOrder: number
  name: string
  state: StepState
  deadline: string | null
}

export type ActionType =
  'EXTERNAL_SEND' | 'TRANSFER' | 'EXPENSE' | 'CONTRACT' | 'NOTICE' | 'CONFIRMATION'

// GET /events/{id}/actions 한 줄 (승인 대기 행에 쓰는 필드만)
export interface EventAction {
  id: string
  type: ActionType
  title: string
  subtitle: string | null
  dueDate: string | null
}
