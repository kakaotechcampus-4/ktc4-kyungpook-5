import type { components } from '@/shared/api/schema'
import type { DraftStep } from './types'

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
  // 이번 화면에서 generation_writing을 받았는가(#388). 모델이 초안 첫 글자를 보낸 뒤다.
  writing?: boolean
  // 이번 화면에서 받은 작성 중 단계(#389). 검증 전이며 저장된 단계가 아니다.
  steps?: DraftStep[]
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
// 행사마다 따로 둔다(#342). A 행사의 결과를 확인하는 동안에도 B 행사 계획은 쓸 수 있다.
export const requestStorageKey = (userId: string, clubId: string, eventId: string) =>
  `planning-request:v1:${userId}:${clubId}:${eventId}`

// A tab journal is a guard against issuing a second POST, never a queue to replay.
export function readRequestText(
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
): string | null {
  if (!userId || !clubId || !eventId) return null
  try {
    return sessionStorage.getItem(requestStorageKey(userId, clubId, eventId))
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
// 서버가 보낸 계획 응답의 최소 모양. 스트림 done과 결과 조회(#342)가 같은 기준을 쓴다.
export function validView(candidate: S['PlanViewOut'] | null | undefined): boolean {
  return (
    !!candidate &&
    Number.isInteger(candidate.baseRevision) &&
    candidate.baseRevision >= 0 &&
    validDraft(candidate.draft) &&
    Array.isArray(candidate.changedFields) &&
    typeof candidate.generationReadiness?.canGenerate === 'boolean' &&
    Array.isArray(candidate.generationReadiness.reasons) &&
    (candidate.reply === null || typeof candidate.reply === 'string') &&
    (candidate.generationResult === null ||
      ['generated', 'failed', 'needs_clarification'].includes(candidate.generationResult?.status))
  )
}

// 결과를 모르는 요청을 요청 키로 조회한 뒤 할 일 (#342).
//   completed + 읽을 수 있는 응답 → apply: 정상 응답을 받은 것처럼 이어 간다
//   completed + 읽을 수 없는 응답 → release: 저장은 끝났으니 잠금을 풀고 저장된 계획을 다시 읽는다
//   not_saved                  → release: 저장되지 않았으니 잠금을 풀고 다시 보내게 한다
//   processing                 → wait: 잠시 뒤 다시 조회한다
export function recoveryStep(lookup: S['PlanRequestOut']): 'apply' | 'release' | 'wait' {
  if (lookup.status === 'processing') return 'wait'
  return lookup.status === 'completed' && validView(lookup.result) ? 'apply' : 'release'
}

// 결과를 모르는 요청을 대화 화면(P1)에서 확인할지 정한다(#368).
// 채팅은 서버가 실제 초안 생성 직전에 보내는 generation_started를 받았을 때만 초안 요청으로 본다.
//   버튼 「이 조건으로 초안 만들기」 → 끊김                        → false: 초안 생성 화면에서 확인
//   채팅 "인원 40명으로 바꿔 줘" → 끊김                           → true: 대화 화면에서 확인
//   채팅 "이대로 초안 만들어 줘" → generation_started → 끊김      → false: 초안 생성 화면에서 확인
// 끊긴 뒤 서버에서 초안까지 만들어졌다면 조회 결과로 알게 되고, 그때 P2로 넘어간다.
export function checksInChat(
  request: Pick<PlanningRequest, 'kind' | 'started'> | null | undefined,
  phase: GenerationPhase | undefined,
): boolean {
  return phase === 'unknown' && request?.kind === 'chat' && !request.started
}

export function parseRequest(
  raw: string | null,
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
): PlanningRequest | null {
  if (!raw) return null
  try {
    const r = JSON.parse(raw) as PlanningRequest
    if (
      r.version !== 1 ||
      r.userId !== userId ||
      r.clubId !== clubId ||
      r.eventId !== eventId ||
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
  sessionStorage.setItem(
    requestStorageKey(request.userId, request.clubId, request.eventId),
    JSON.stringify(request),
  )
  window.dispatchEvent(new Event(CHANGE))
}
export function removeRequest(request: PlanningRequest) {
  // A late completion must not delete a different request's journal.
  const { userId, clubId, eventId } = request
  const raw = readRequestText(userId, clubId, eventId)
  if (parseRequest(raw, userId, clubId, eventId)?.key !== request.key) return
  sessionStorage.removeItem(requestStorageKey(userId, clubId, eventId))
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

// 생성 화면에만 있는 끝 상태. 요청 기록(GenerationPhase)에는 남기지 않는다.
//   done   → 새 초안을 확인했고, 잠시 보여 준 뒤 계획 검토로 넘어간다
//   failed → 생성이 끝났지만 초안이 없다. 그 자리에서 이유를 보이고 대화로 돌려보낸다
export type GenerationScreenPhase = GenerationPhase | 'done' | 'failed'
export type GenerationRowState = 'done' | 'active' | 'pending' | 'failed' | 'unknown'

// 생성 화면의 진행 줄. 각 줄은 서버나 화면이 실제로 지나는 구간 하나다(PRODUCT 원칙 4).
//   조건 확인    요청을 보내고 생성 가능 여부를 확인한다. 채팅은 서버가 확인한 뒤에야 generation_started를 보낸다
//   초안 작성    generation_started ~ generation_finished. 모델이 초안을 쓰는 구간
//   저장 확인    generation_finished ~ 스트림 done. 서버가 검증한 초안을 저장한다
//   계획 불러오기 저장된 준비 순서를 다시 읽어 이번 요청의 결과인지 확인한다
export const GENERATION_ROWS = ['조건 확인', '초안 작성', '저장 확인', '계획 불러오기'] as const
const ROW_OF: Partial<Record<GenerationPhase, number>> = {
  requesting: 0,
  generating: 1,
  verifying: 2,
  loading: 3,
}

// 화면 상태 → 진행 줄 상태.
//   generating                    → ✓ 조건 확인 | ● 초안 작성 | ○ 저장 확인 | ○ 계획 불러오기
//   failed (초안 작성 중 멈춤)      → ✓ 조건 확인 | ! 초안 작성 | ○ ...
//   load-failed (저장은 됐다)       → ✓ ✓ ✓ | ! 계획 불러오기
//   unknown (연결이 끊겨 결과 모름)   → – – | ● 저장 확인 | ○. 서버에 저장됐는지 묻는 중이다
export function generationRows(
  phase: GenerationScreenPhase,
  stoppedAt?: GenerationPhase,
): GenerationRowState[] {
  const states = (current: number, at: GenerationRowState) =>
    GENERATION_ROWS.map((_, index) =>
      index < current ? 'done' : index === current ? at : 'pending',
    ) as GenerationRowState[]
  if (phase === 'done') return GENERATION_ROWS.map(() => 'done')
  if (phase === 'failed') return states((stoppedAt && ROW_OF[stoppedAt]) ?? 1, 'failed')
  if (phase === 'unknown') return ['unknown', 'unknown', 'active', 'pending']
  if (phase === 'load-failed' || phase === 'unconfirmed' || phase === 'changed')
    return states(3, 'failed')
  return states(ROW_OF[phase] ?? 0, 'active')
}

// 「초안 작성」 줄 옆 문구(#388). 서버가 보낸 신호로만 바꾼다.
//   generation_started 받음          → 토리가 생각 중이에요     (모델이 추론하는 동안, 실측 p50 4~5초)
//   generation_writing 받음          → 초안을 작성하는 중이에요 (첫 글자부터 끝까지, 실측 p50 7~8초)
//   그 밖(다음 줄로 넘어감·새로고침 뒤 확인) → 없음. 시작을 보지 못했으면 지어내지 않는다
export function draftingNote(flow: GenerationFlow, ended: boolean): string | null {
  if (ended || flow.phase !== 'generating') return null
  return flow.writing ? '초안을 작성하는 중이에요' : '토리가 생각 중이에요'
}

// 작성 중 단계 신호를 목록에 붙인다(#389). 서버는 0번부터 차례로 하나씩 보낸다.
// 다음 차례가 아닌 신호(중복·건너뜀)는 버린다. 목록이 최종 초안 순서와 어긋나 보이지 않게 한다.
//   [] + {index 0, 담당 인원 배치}            → [담당 인원 배치]
//   [담당 인원 배치] + {index 0, …} (중복)     → 그대로
//   [담당 인원 배치] + {index 2, …} (건너뜀)   → 그대로
export function appendDraftStep(steps: DraftStep[], step: DraftStep | undefined): DraftStep[] {
  if (!step || step.index !== steps.length || !step.name) return steps
  return [...steps, step]
}

// 「초안 작성」 아래 단계 목록(#389). 없으면 null이라 펼침 버튼도 그리지 않는다.
//   작성 중    → 앞 단계는 끝남(✓), 마지막 단계는 진행 중(●). 모델이 지금 그 단계를 쓰고 있다
//   생성 성공 뒤 → 모두 끝남(✓). 다음 줄(저장 확인)로 넘어가도 목록은 그대로 둔다
//   생성 실패   → null. 검증 전 목록이라 저장된 초안처럼 남기지 않는다
export function draftStepRows(
  flow: GenerationFlow,
  failed: boolean,
): { step: DraftStep; state: 'done' | 'active' }[] | null {
  if (failed || !flow.steps?.length) return null
  const last = flow.steps.length - 1
  return flow.steps.map((step, index) => ({
    step,
    state: index === last && flow.phase === 'generating' ? 'active' : 'done',
  }))
}

// 지금 초안이 있는데 다시 만드는 경우의 문구. 첫 생성과 같은 말을 쓰면 지금 초안이 어떻게 되는지 알 수 없다.
export const regenerationCopy: Partial<Record<GenerationPhase, { title: string; detail: string }>> =
  {
    generating: {
      title: '새 초안을 만들고 있어요',
      detail: '다 만들면 지금 초안을 새 초안으로 바꿔요. 그 전까지 지금 초안은 그대로예요.',
    },
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
    title: '처리 결과를 확인하고 있어요',
    detail:
      '연결이 끊겨 응답을 받지 못했어요. 서버에 저장됐는지 확인하고, 저장됐으면 이어서 보여 드릴게요.',
  },
  changed: {
    title: '생성 뒤 계획에 다른 변경이 있어요',
    detail: '이번 생성 이후의 변경이 있어요. 현재 저장된 계획을 확인해 주세요.',
  },
}
