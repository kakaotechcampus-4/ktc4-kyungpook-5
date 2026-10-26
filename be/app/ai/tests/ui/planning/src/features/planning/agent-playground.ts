// 로컬 테스트 계약. history는 AI가 반환한 형태 그대로 다음 요청에 전달한다.
import { toFacts } from './playground'
import type { Conditions } from './playground'
import type { Fact } from './playground'
import type { PlanFactKey } from './types'
import type { GenerationResult, GenerationState } from './generation-playground'

export { testApi } from './playground'

export interface AgentDraft {
  conditions: Conditions
  condition_meta: Partial<
    Record<
      keyof Conditions,
      {
        status: 'tentative' | 'specified'
        evidence: { message_id: string; quote: string }
      }
    >
  >
  deferred_topics: string[]
}
export interface RecordLookup {
  status: 'available' | 'not_found' | 'failed' | 'rejected'
  query: string | null
  reason: string | null
  result: {
    facts: Fact[]
    not_found: string[]
    conflicts: { description: string; values: Fact[] }[]
  } | null
}
export interface AgentResult {
  reply: string
  draft: AgentDraft
  history: unknown[]
  executions: {
    tool_call_id: string
    name: string
    result:
      | RecordLookup
      | {
          status: 'applied' | 'unchanged' | 'rejected'
          changed_fields?: string[]
          reason: string | null
        }
      | GenerationResult
  }[]
  model_calls: number
  limit_reached: boolean
  prompt_version: string
  record_lookup: RecordLookup | null
  generation: GenerationState
  generation_result: GenerationResult | null
  generation_model_calls: number
  preview_is_current: boolean
}
export interface AgentHealth {
  model: string
  agent_version: string
  fixture_count: number
  record_search: boolean
  plan_generation: boolean
}

export const TOPIC_LABELS: Record<string, string> = {
  title: '행사 이름',
  event_type: '종류',
  headcount: '인원',
  fee_per_person: '참가비',
  dates: '일정',
  location: '장소',
  budget_total: '예산 상한',
}

export function toAgentFacts(draft: AgentDraft) {
  const facts = toFacts(draft.conditions)
  const fields: Partial<Record<keyof Conditions, PlanFactKey>> = {
    title: '행사 이름',
    event_type: '종류',
    headcount: '예상 인원',
    fee_per_person: '참가비',
    start_date: '일정',
    end_date: '일정',
    location: '장소',
  }
  for (const [field, meta] of Object.entries(draft.condition_meta)) {
    const key = fields[field as keyof Conditions]
    const fact = key ? facts[key] : undefined
    if (fact && meta?.status === 'tentative') {
      fact.decided = false
      fact.note = '잠정'
    }
  }
  return facts
}
