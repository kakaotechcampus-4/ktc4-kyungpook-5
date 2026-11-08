// 메인 토리 데스크(브리핑 + 카드 답)의 데이터 모양.
// 지금은 ?demo 시안에서만 쓴다. 서버가 붙으면 브리핑 요약 API와 토리 응답의 card 필드가 이 모양을 따른다.
import type { EventSummary } from '@/features/events/types'
import type { components } from '@/shared/api/schema'

// 브리핑 「지금 챙길 것」 한 줄의 종류. 3일 안에 끝나는 단계, 승인을 기다리는 행동, 계정에 배정된 할 일.
export type BriefingKind = 'deadline' | 'approval' | 'task'

export interface BriefingItem {
  id: string
  kind: BriefingKind
  title: string
  // 어느 행사나 회의에서 온 일인지. "2026 봄 MT | 입금 확인 단계"처럼 화면에 그대로 쓴다.
  source: string
  // 한국 날짜 "YYYY-MM-DD". 승인 대기는 기한이 없어 null이다.
  dueDate: string | null
  // 같은 행사에 같은 종류가 더 있으면 "외 n건"으로 묶는다.
  moreCount?: number
  href: string
  // 이 줄을 토리에게 이어 물을 때 보낼 말. 없으면 「토리에게 묻기」를 띄우지 않는다.
  ask?: string
}

export interface Briefing {
  items: BriefingItem[]
  // 진행 중과 계획 중인 행사. 끝난 행사는 넣지 않는다.
  events: EventSummary[]
}

export interface StatusStep {
  name: string
  dueDate: string | null
}

export interface EventStatusData {
  event: EventSummary
  current: StatusStep | null
  next: StatusStep[]
  approvals: string[]
  // 예산과 쓴 돈은 서버가 장부에서 더한 값이다. 예산을 정하지 않았으면 budget이 null.
  budget: number | null
  spent: number
}

export interface ApprovalGroup {
  eventTitle: string
  href: string
  titles: string[]
}

export interface TaskRow {
  id: string
  title: string
  assignee: string | null
  dueDate: string | null
}

export interface HandoffCondition {
  label: string
  value: string
}

export interface RelatedRow {
  title: string
  source: string
  status: string
  href: string
  action: string
}

// 토리 답 아래에 붙는 카드. 답 종류마다 하나씩이다.
export type ToriCard =
  | { type: 'events'; events: EventSummary[] }
  | { type: 'event_status'; status: EventStatusData }
  | { type: 'approvals'; groups: ApprovalGroup[] }
  | {
      type: 'tasks'
      title: string
      tasks: TaskRow[]
      footer: { label: string; href: string }
    }
  | { type: 'handoff'; title: string; conditions: HandoffCondition[]; href: string }
  | { type: 'related'; title: string; rows: RelatedRow[] }

export interface ToriDeskReply {
  reply: string
  card?: ToriCard
  // 이 답 다음에 이어서 물어볼 만한 말. 마지막 답에만 버튼으로 보인다.
  suggestions?: string[]
  // 지금 서버 응답(자료 검색 답 등). 있으면 기존 답 화면으로 그린다.
  legacy?: components['schemas']['ToriMessageOut']
}

// 한국 날짜 기준 오늘 "YYYY-MM-DD"
export function todayKst(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
}

export function daysUntil(date: string, today = todayKst()): number {
  return Math.round((Date.parse(date) - Date.parse(today)) / 86_400_000)
}

// 남은 날을 짧게. 지났으면 "지남", 오늘·내일은 말로, 그 뒤는 D-n.
export function dueLabel(date: string | null, today = todayKst()): string {
  if (!date) return '기한 없음'
  const left = daysUntil(date, today)
  if (left < 0) return '지남'
  if (left === 0) return '오늘'
  if (left === 1) return '내일'
  return `D-${left}`
}

// "2026-11-19" → "11/19"
export function shortDay(date: string): string {
  const [, month, day] = date.split('-')
  return `${Number(month)}/${Number(day)}`
}
