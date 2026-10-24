// 테스트 UI의 생성 계약. 버튼 요청에는 사용자 발화를 만들지 않는다.
import type { AgentDraft } from './agent-playground'
import { STEP_CATALOGUE } from './catalogue'
import type { Fact } from './playground'
import type { PlanStep, StepActor, StepPhase } from './types'

export interface PlanPreview {
  id: string
  basis_draft: AgentDraft
  trigger: { source: 'chat' | 'button'; request_id: string; quote?: string }
  steps: {
    code: string
    name: string
    phase: 'PREPARATION' | 'RECRUITING' | 'EXECUTION'
    actor: 'AI' | 'APPROVAL_REQUIRED' | 'MANUAL'
    purpose: string
    starts_at: string | null
    deadline: string | null
    actions: { type: string; title: string; due_date: string | null }[]
  }[]
  excluded_steps: { code: string; reason: string }[]
  assumptions: { content: string; sources: Fact['sources'] }[]
  open_questions: string[]
  warnings: string[]
}
export interface GenerationState {
  offer: {
    id: string
    status: 'pending' | 'deferred'
    summary: string
    basis_draft: AgentDraft
  } | null
  preview: PlanPreview | null
  condition_change_pending: boolean
  pending_condition_fields: string[]
}
export interface GenerationResult {
  status: 'generated' | 'needs_clarification' | 'failed'
  preview: PlanPreview | null
  reason: string | null
  model_calls: number
}
export interface GenerationUpdate {
  generation: GenerationState
  result: GenerationResult
}
export interface AgentSession {
  draft: AgentDraft
  history: unknown[]
  generation: GenerationState
}
export interface ChatRequest extends AgentSession {
  current_message: { id: string; role: 'user'; text: string }
  reference_date: string
  timezone: string
}
export interface ButtonRequest extends AgentSession {
  request_id: string
  reference_date: string
  timezone: string
}
export type PendingRequest =
  { source: 'chat'; body: ChatRequest } | { source: 'button'; body: ButtonRequest }

export function newSession(): AgentSession {
  return {
    draft: { conditions: {}, condition_meta: {}, deferred_topics: [] },
    history: [],
    generation: {
      offer: null,
      preview: null,
      condition_change_pending: false,
      pending_condition_fields: [],
    },
  }
}

export function latestToolCalls(history: unknown[]): unknown[] {
  // 전체 SDK 응답 대신 이번 사용자 발화 이후의 Tool 인자만 진단 화면에 보여준다.
  let start = 0
  for (let i = history.length - 1; i >= 0; i--) {
    const message = history[i]
    if (message && typeof message === 'object' && 'type' in message && message.type === 'human') {
      start = i + 1
      break
    }
  }
  return history
    .slice(start)
    .flatMap((message) =>
      message &&
      typeof message === 'object' &&
      'tool_calls' in message &&
      Array.isArray(message.tool_calls)
        ? message.tool_calls
        : [],
    )
}

export function previewIsCurrent(session: AgentSession): boolean {
  const basis = session.generation.preview?.basis_draft
  if (!basis || session.generation.condition_change_pending) return false
  const fields = new Set([
    ...Object.keys(basis.conditions),
    ...Object.keys(session.draft.conditions),
  ])
  for (const key of fields) {
    const field = key as keyof AgentDraft['conditions']
    if ((basis.conditions[field] ?? null) !== (session.draft.conditions[field] ?? null))
      return false
  }
  const meta = (draft: AgentDraft) =>
    Object.entries(draft.condition_meta)
      .map(([key, value]) => `${key}:${value?.status}`)
      .sort()
      .join('|')
  return (
    meta(basis) === meta(session.draft) &&
    [...basis.deferred_topics].sort().join('|') ===
      [...session.draft.deferred_topics].sort().join('|')
  )
}

export function latestUserMessage(history: unknown[]): { id: unknown; content: unknown } | null {
  // Tool이 인용한 근거를 실제 메시지와 비교하되 응답 메타정보는 노출하지 않는다.
  for (let i = history.length - 1; i >= 0; i--) {
    const message = history[i]
    if (message && typeof message === 'object' && 'type' in message && message.type === 'human') {
      return {
        id: 'id' in message ? message.id : null,
        content: 'content' in message ? message.content : null,
      }
    }
  }
  return null
}

const PHASES: Record<PlanPreview['steps'][number]['phase'], StepPhase> = {
  PREPARATION: '사전 준비',
  RECRUITING: '모집 · 확정',
  EXECUTION: '행사 진행 · 마무리',
}
const ACTORS: Record<PlanPreview['steps'][number]['actor'], StepActor> = {
  AI: 'AI 실행',
  APPROVAL_REQUIRED: '승인 필요',
  MANUAL: '직접 수행',
}
const ACTIONS: Record<string, string> = {
  NOTICE: '공지',
  EXTERNAL_SEND: '개별 연락',
  CONTRACT: '계약',
  TRANSFER: '이체·수금',
  EXPENSE: '지출',
}
export function toPreviewSteps(preview: PlanPreview): PlanStep[] {
  const date = (value: string | null) =>
    value ? new Date(value).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' }) : '미정'
  return preview.steps.map((step) => ({
    id: `${preview.id}:${step.code}`,
    name: step.name,
    phase: PHASES[step.phase],
    actor: ACTORS[step.actor],
    desc: [
      step.purpose,
      ...step.actions.map(
        (action) => `예정된 일: ${action.title} · 기한 ${action.due_date ?? '미정'}`,
      ),
    ].join('\n'),
    date:
      step.starts_at || step.deadline ? `${date(step.starts_at)} ~ ${date(step.deadline)}` : '미정',
    actionLabel: [
      ...new Set(step.actions.map((action) => ACTIONS[action.type] ?? action.type)),
    ].join(' · '),
  }))
}

// 기존 FE 카탈로그와 BE의 다른 코드를 명시적으로 변환한다. 단계 표시는 서버의 이름을 사용한다.
const FE_CODE: Record<string, string> = {
  ASSIGN_ROLES: 'ASSIGN_STAFF',
  RESEARCH_VENUE: 'SCOUT_VENUE',
  DEMAND_SURVEY: 'SURVEY_DEMAND',
  CONFIRM_DETAILS: 'CONFIRM_HEADCOUNT',
  PRE_EVENT_NOTICE: 'PRE_NOTICE',
}
export function excludedStepName(code: string): string {
  return STEP_CATALOGUE.find((step) => step.code === (FE_CODE[code] ?? code))?.name ?? code
}
