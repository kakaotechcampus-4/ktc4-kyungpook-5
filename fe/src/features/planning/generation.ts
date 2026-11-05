import type { components } from '@/shared/api/schema'

type S = components['schemas']
export type GenerationPhase =
  | 'requesting'
  | 'generating'
  | 'verifying'
  | 'loading'
  | 'load-failed'
  | 'unconfirmed'
  | 'unknown'
  | 'changed'
export interface GenerationFlow {
  phase: GenerationPhase
  draft: S['PlanDraftOut']
}
export interface PlanningRequest {
  version: 1
  userId: string
  clubId: string
  eventId: string
  key: string
  kind: 'chat' | 'button'
  body: S['PlanChatIn'] | S['PlanGenerateIn']
  baseline: { baseRevision: number; planRevision: number; steps: { id: string }[] }
  draft: S['PlanDraftOut']
  started: boolean
  result?: S['PlanViewOut']
  recovery?: 'load-failed' | 'unconfirmed' | 'changed'
}

const CHANGE = 'planning-request-change'
export const requestStorageKey = (userId: string, clubId: string) =>
  `planning-request:v1:${userId}:${clubId}`

// A tab journal is a guard against issuing a second POST, never a queue to replay.
export function readRequestText(userId: string | undefined, clubId: string | null): string | null {
  if (!userId || !clubId) return null
  try {
    return sessionStorage.getItem(requestStorageKey(userId, clubId))
  } catch {
    return 'unavailable'
  }
}
export function validDraft(draft: S['PlanDraftOut'] | undefined): boolean {
  if (!draft?.conditions || !draft.conditionMeta || !Array.isArray(draft.deferredTopics))
    return false
  const c = draft.conditions
  return (
    ['title', 'eventType', 'startDate', 'endDate', 'location'].every(
      (key) => c[key as keyof typeof c] === null || typeof c[key as keyof typeof c] === 'string',
    ) &&
    ['headcount', 'feePerPerson', 'budgetTotal'].every(
      (key) =>
        c[key as keyof typeof c] === null ||
        (typeof c[key as keyof typeof c] === 'number' && Number.isFinite(c[key as keyof typeof c])),
    )
  )
}
export function parseRequest(
  raw: string | null,
  userId: string | undefined,
  clubId: string | null,
): PlanningRequest | null {
  if (!raw) return null
  try {
    const r = JSON.parse(raw) as PlanningRequest
    if (
      r.version !== 1 ||
      r.userId !== userId ||
      r.clubId !== clubId ||
      typeof r.eventId !== 'string' ||
      typeof r.key !== 'string' ||
      !['chat', 'button'].includes(r.kind) ||
      !r.body ||
      !validDraft(r.draft) ||
      !Number.isInteger(r.baseline?.baseRevision) ||
      !Number.isInteger(r.baseline?.planRevision) ||
      !Array.isArray(r.baseline?.steps) ||
      !r.baseline.steps.every((step) => typeof step.id === 'string') ||
      r.baseline.baseRevision < 0 ||
      r.baseline.planRevision < 0 ||
      r.body.baseRevision !== r.baseline.baseRevision ||
      typeof r.started !== 'boolean'
    )
      return null
    if (r.recovery !== undefined && !['load-failed', 'unconfirmed', 'changed'].includes(r.recovery))
      return null
    if (
      r.result &&
      (!validDraft(r.result.draft) ||
        !Number.isInteger(r.result.baseRevision) ||
        !['generated', 'needs_clarification', 'failed'].includes(
          r.result.generationResult?.status ?? '',
        ))
    )
      return null
    return r
  } catch {
    return null
  }
}
export function subscribeRequest(callback: () => void) {
  window.addEventListener(CHANGE, callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener(CHANGE, callback)
    window.removeEventListener('storage', callback)
  }
}
export function writeRequest(request: PlanningRequest) {
  sessionStorage.setItem(requestStorageKey(request.userId, request.clubId), JSON.stringify(request))
  window.dispatchEvent(new Event(CHANGE))
}
export function removeRequest(request: PlanningRequest) {
  // A late completion must not delete a different request's journal.
  const raw = readRequestText(request.userId, request.clubId)
  if (parseRequest(raw, request.userId, request.clubId)?.key !== request.key) return
  sessionStorage.removeItem(requestStorageKey(request.userId, request.clubId))
  window.dispatchEvent(new Event(CHANGE))
}

export function generatedSnapshotStatus(
  request: PlanningRequest,
  result: S['PlanViewOut'],
  snapshot: S['PlanStepsSnapshotOut'],
): 'new' | 'unconfirmed' | 'changed' {
  if (
    result.generationResult?.status !== 'generated' ||
    result.baseRevision !== request.baseline.baseRevision + 1
  )
    return 'unconfirmed'
  if (snapshot.baseRevision > result.baseRevision) return 'changed'
  if (
    snapshot.baseRevision !== result.baseRevision ||
    snapshot.planRevision <= request.baseline.planRevision ||
    !snapshot.steps.length
  )
    return 'unconfirmed'
  const oldIds = new Set(request.baseline.steps.map((step) => step.id))
  const ids = snapshot.steps.map((step) => step.id)
  return new Set(ids).size === ids.length && ids.every((id) => !oldIds.has(id))
    ? 'new'
    : 'unconfirmed'
}

export const generationCopy: Record<GenerationPhase, { title: string; detail: string }> = {
  requesting: {
    title: '생성 요청을 확인하고 있어요',
    detail: '정한 조건으로 초안을 만들 수 있는지 확인하고 있어요.',
  },
  generating: {
    title: '초안을 만들고 있어요',
    detail: '정한 조건에 맞춰 준비 순서와 일정을 만들고 있어요.',
  },
  verifying: {
    title: '생성 결과를 확인하고 있어요',
    detail: '결과와 저장 여부를 확인한 뒤 계획 검토로 이어갈게요.',
  },
  loading: {
    title: '저장된 초안을 불러오고 있어요',
    detail: '새 초안의 준비 순서를 확인하고 있어요.',
  },
  'load-failed': {
    title: '초안은 저장됐지만 불러오지 못했어요',
    detail: '연결을 확인한 뒤 초안을 다시 불러와 주세요.',
  },
  unconfirmed: {
    title: '새 초안을 확인하지 못했어요',
    detail: '이번 요청으로 저장된 준비 순서를 다시 확인해 주세요.',
  },
  unknown: {
    title: '처리 결과를 확인하지 못했어요',
    detail: '요청이 처리됐을 수 있어요. 같은 요청의 결과를 확인하기 전에는 다시 만들지 않아요.',
  },
  changed: {
    title: '생성 뒤 계획에 다른 변경이 있어요',
    detail: '이번 생성 이후의 변경이 있어요. 현재 저장된 계획을 확인해 주세요.',
  },
}
