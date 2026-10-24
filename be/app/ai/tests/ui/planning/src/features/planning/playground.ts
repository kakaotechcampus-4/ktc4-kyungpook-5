// 테스트 전용 wire 타입. 실제 공개 BE 계약은 합의 후 별도로 생성한다.
import type { PlanFacts } from './types'

export type Conditions = Partial<{
  title: string | null
  event_type: string | null
  headcount: number | null
  fee_per_person: number | null
  start_date: string | null
  end_date: string | null
  location: string | null
  budget_total: number | null
}>
export interface QuestionState {
  event_id: string
  asked_fields?: string[]
  deferred_fields?: string[]
  last_question_fields?: string[]
}
export interface Fact {
  content: string
  sources: { record_id: string; file_name: string; location: { label: string } }[]
}
export interface TurnResult {
  reply: string
  collected: Conditions
  pending_clarifications: unknown[]
  next_question_state: QuestionState
  question: { text: string; quick_replies: string[] } | null
  readiness: { ready_to_generate: boolean; reasons: string[] }
  record_lookup: {
    status: string
    error_code: string | null
    clarification: string | null
    result: {
      status: string
      cards: Fact[]
      not_found: string[]
      conflicts: { description: string; values: Fact[] }[]
    } | null
  }
}
export async function testApi<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/__planning-test/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(
      typeof data?.detail === 'string'
        ? data.detail
        : '요청을 처리하지 못했어요. AI 서버와 입력을 확인해 주세요.',
    )
  }
  return response.json() as Promise<T>
}

export function toFacts(c: Conditions): PlanFacts {
  const fact = (value: string | number | null | undefined) =>
    value == null ? undefined : { value: String(value), decided: true }
  const types: Record<string, string> = {
    MT: 'MT',
    WELCOME: '신환회',
    WORKSHOP: '워크숍',
    PICNIC: '소풍',
    ACADEMIC: '학술 행사',
    ETC: '기타',
  }
  return {
    '행사 이름': fact(c.title),
    종류: fact(c.event_type ? (types[c.event_type] ?? c.event_type) : null),
    '예상 인원': fact(c.headcount == null ? null : `${c.headcount}명`),
    참가비: fact(
      c.fee_per_person == null
        ? null
        : c.fee_per_person === 0
          ? '무료 (0원)'
          : `${c.fee_per_person.toLocaleString()}원`,
    ),
    일정:
      c.start_date || c.end_date
        ? {
            value: `${c.start_date ?? '미정'} ~ ${c.end_date ?? '미정'}`,
            decided: !!c.start_date && !!c.end_date,
          }
        : undefined,
    장소: fact(c.location),
  }
}
