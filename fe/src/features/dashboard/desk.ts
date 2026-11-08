// 메인 토리 데스크(브리핑 + 카드 답)의 데이터 모양.
// 브리핑은 GET /clubs/{id}/tori/briefing, 답은 POST /clubs/{id}/tori/messages의 card를 그대로 쓴다.
// 서버는 주소 대신 행사·할 일·회의 ID를 주고, 화면 주소는 여기서 만든다.
import { useSearchParams } from 'react-router-dom'
import type { EventSummary } from '@/features/events/types'
import type { components } from '@/shared/api/schema'
import { supportsDemoPath } from '@/shared/lib/demo'

type S = components['schemas']
type Out = S['ToriMessageOut']

// 브리핑 「확인할 일」 한 줄. 3일 안에 끝나는 단계, 승인을 기다리는 행동, 계정에 배정된 할 일.
export type BriefingItem = S['ToriBriefingItem']
export type BriefingKind = BriefingItem['kind']

export interface Briefing {
  items: BriefingItem[]
  // 진행 중과 계획 중인 행사. 끝난 행사는 넣지 않는다.
  events: EventSummary[]
}

// 브리핑을 아직 못 받았거나 받지 못했어도 입력 상자는 쓸 수 있게, 상태를 함께 넘긴다.
export type BriefingState =
  | { status: 'ready'; data: Briefing }
  | { status: 'loading' }
  | { status: 'error'; retry: () => void }

// 토리 답 아래에 붙는 카드. 서버 카드에 「내 할 일」 하나를 더한다.
// 내 할 일 답은 서버가 card 대신 tasks로 주므로 여기서 카드로 바꾼다.
export type ServerCard = NonNullable<Out['card']>
// 카드에 그리는 칸만 둔다.
export type MyTaskItem = Pick<
  S['ConfirmedTaskOut'],
  'id' | 'title' | 'kind' | 'assigneeName' | 'dueAt' | 'scheduledAt'
>
export type MyTasks = Omit<S['ToriTasks'], 'items'> & { items: MyTaskItem[] }
export type ToriCard = ServerCard | { type: 'my_tasks'; tasks: MyTasks }
export type Navigation = NonNullable<Out['navigation']>

export interface ToriDeskReply {
  reply: string
  card?: ToriCard | null
  // 이 답 다음에 이어서 물어볼 만한 말. 마지막 답에만 버튼으로 보인다.
  suggestions?: string[]
  // 토리가 하지 않는 일을 할 수 있는 화면.
  navigation?: Navigation | null
  // 자료 찾기 답이 행사·기간을 되물을 때. 다음 질문에 이 맥락을 붙여 보낸다.
  clarification?: S['ToriClarification'] | null
  // 자료 찾기 답. 출처와 검색 결과가 있어 기존 답 화면으로 그린다.
  records?: Out
}

export function toDeskReply(result: Out): ToriDeskReply {
  const card: ToriCard | null =
    result.card ?? (result.tasks ? { type: 'my_tasks', tasks: result.tasks } : null)
  return {
    reply: result.reply,
    card,
    suggestions: result.suggestions,
    // 계획 넘기기 카드에는 이동 버튼이 따로 있다.
    navigation: card?.type === 'handoff' ? null : result.navigation,
    clarification: result.clarification,
    records: result.records || result.recordAnswer ? result : undefined,
  }
}

// 화면 주소. 브리핑 줄은 행사 일이면 행사 상세, 할 일이면 회의 화면의 확정한 할 일로 간다.
export const eventPath = (eventId: string) => `/events/${encodeURIComponent(eventId)}`
export const meetingPath = (meetingId: string) => `/meetings/${encodeURIComponent(meetingId)}`

export function briefingPath(item: BriefingItem): string {
  if (item.kind === 'task')
    return item.taskId ? `/meetings?${new URLSearchParams({ taskId: item.taskId })}` : '/meetings'
  return item.eventId ? eventPath(item.eventId) : '/events'
}

// 시안(?demo)에서는 시연을 지원하는 화면으로 갈 때 ?demo를 이어 붙인다.
export function useDeskPath(): (path: string) => string {
  const demo = useSearchParams()[0].has('demo')
  return (path) => {
    if (!demo) return path
    const [pathname, query] = path.split('?')
    if (!supportsDemoPath(pathname)) return path
    return `${pathname}?${query ? `${query}&` : ''}demo`
  }
}

// 한국 날짜 기준 오늘 "YYYY-MM-DD"
export function todayKst(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' })
}

// 서버 시각(ISO)을 한국 날짜 "YYYY-MM-DD"로
export function kstDay(value: string | null): string | null {
  return value ? new Date(value).toLocaleDateString('en-CA', { timeZone: 'Asia/Seoul' }) : null
}

export function daysUntil(date: string, today = todayKst()): number {
  return Math.round((Date.parse(date) - Date.parse(today)) / 86_400_000)
}

// 남은 날을 짧게. 지났으면 "지남", 오늘·내일은 말로, 그 뒤는 D-n.
export function dueLabel(date: string | null | undefined, today = todayKst()): string {
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
