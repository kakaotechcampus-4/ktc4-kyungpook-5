// 「지금 할 일」(L2): 운영진 차례인 Action을 행사 전체에서 모아 순서를 정한다.
// 화면 없이 확인할 수 있게 계산만 모아 둔다(tests/todo.test.mjs).
import { draftView, isDraftTarget } from '@/features/events/actionDraft'
import type { EventAction, EventStep } from '@/features/events/types'

// 행 하나가 무엇을 기다리는지
// drafting: 토리가 쓰는 중 · draftFailed: 토리가 초안을 못 씀 · failed: 처리 실패
// question: 토리의 질문 · review: 검토 후 승인 · manual: 직접 처리 후 완료 표시 · execute: 승인됨, 밖에서 실행할 차례
export type TodoKind =
  'drafting' | 'draftFailed' | 'failed' | 'question' | 'review' | 'manual' | 'execute'

// 토리가 일하는 중이거나 막힌 일을 먼저, 그다음 검토, 실행 순으로 보인다
const ORDER: TodoKind[] = [
  'drafting',
  'draftFailed',
  'failed',
  'question',
  'review',
  'manual',
  'execute',
]

export interface TodoItem {
  kind: TodoKind
  action: EventAction
  // 속한 단계. 단계에 안 묶인 질문은 없다.
  step?: EventStep
  // 스테퍼에서 몇 번째 단계인지(1부터)
  position?: number
}

export function todoKind(action: EventAction): TodoKind | null {
  if (action.type === 'CONFIRMATION') return action.status === 'PENDING' ? 'question' : null
  switch (action.status) {
    case 'PENDING': {
      const view = draftView(action)
      if (view === 'DRAFTING') return 'drafting'
      if (view === 'FAILED') return 'draftFailed'
      return action.approveNeeded === false ? 'manual' : 'review'
    }
    case 'APPROVED':
      return 'execute'
    case 'FAILED':
      return 'failed'
    default:
      return null
  }
}

// 아직 시작하지 않은 단계의 일은 운영진 차례가 아니라서 뺀다.
// 미리 승인할 수는 있지만 그건 단계 모달에서 한다. 기한이 빠른 일을 같은 묶음 안에서 위로 올린다.
export function todoList(actions: EventAction[], steps: EventStep[]): TodoItem[] {
  const items: TodoItem[] = []
  for (const action of actions) {
    const kind = todoKind(action)
    if (!kind) continue
    const index = action.stepId ? steps.findIndex((s) => s.id === action.stepId) : -1
    const step = index >= 0 ? steps[index] : undefined
    if (step?.state === 'TODO') continue
    items.push({ kind, action, step, position: step ? index + 1 : undefined })
  }
  const due = (a: EventAction) => (a.dueDate ? Date.parse(a.dueDate) : Number.POSITIVE_INFINITY)
  return items.sort(
    (a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind) || due(a.action) - due(b.action),
  )
}

// 토리가 쓴 초안 중 운영진이 아직 승인하지도 고치지도 않은 것
export function isFreshDraft(action: EventAction): boolean {
  return action.status === 'PENDING' && draftView(action) === 'READY_AI'
}

// 목록 위 토리 한 줄의 재료. 쓰는 중이 있으면 그쪽을 먼저 알린다.
export interface ToriSummary {
  drafting: number
  ready: number
  // 초안에 남은 빈칸 수(같은 이름도 초안마다 센다)
  blanks: number
  // 초안이 모두 한 단계에 속하면 그 단계 이름
  stepName?: string
}

export function toriSummary(items: TodoItem[]): ToriSummary | null {
  const drafting = items.filter((i) => i.kind === 'drafting')
  const ready = items.filter((i) => isFreshDraft(i.action))
  if (drafting.length === 0 && ready.length === 0) return null
  const shown = drafting.length > 0 ? drafting : ready
  const names = new Set(shown.map((i) => i.step?.name))
  const only = names.size === 1 ? [...names][0] : undefined
  return {
    drafting: drafting.length,
    ready: ready.length,
    blanks: ready.reduce((sum, i) => sum + (i.action.contentUnknowns?.length ?? 0), 0),
    stepName: only,
  }
}

// 현재 단계 카드의 "토리가 한 일"에 덧붙일 문장
export function draftSentences(actions: EventAction[]): string[] {
  return actions.flatMap((action) => {
    if (!isDraftTarget(action.type) || action.status !== 'PENDING') return []
    if (draftView(action) === 'DRAFTING') return [`「${action.title}」 초안을 쓰고 있어요.`]
    if (draftView(action) === 'READY_AI') return [`「${action.title}」 초안을 써 뒀어요.`]
    return []
  })
}
