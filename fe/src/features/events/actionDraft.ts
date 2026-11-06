// 토리 본문 초안(#335): Action 카드에 무엇을 보일지, 언제 다시 조회할지, 409를 어떻게 읽을지.
// 화면 없이 확인할 수 있게 계산만 모아 둔다(tests/action-draft.test.mjs).
import type { ActionType, EventAction, StepState } from '@/features/events/types'

// 토리가 본문 초안을 쓰는 종류. 글로 내보내는 일만 대상이다(#332 정한 기본값).
const DRAFT_TYPES: readonly ActionType[] = ['NOTICE', 'EXTERNAL_SEND']

export function isDraftTarget(type: ActionType): boolean {
  return DRAFT_TYPES.includes(type)
}

// 승인 대기 카드의 박스 자리에 보일 것
// NONE: 지금과 같음 · UPCOMING: 아직 시작하지 않은 단계라 초안이 오기 전
export type DraftView = 'NONE' | 'UPCOMING' | 'DRAFTING' | 'READY_AI' | 'READY_USER' | 'FAILED'

export function draftView(action: EventAction, stepState?: StepState): DraftView {
  if (!isDraftTarget(action.type)) return 'NONE'
  switch (action.contentStatus ?? 'NONE') {
    case 'DRAFTING':
      return 'DRAFTING'
    case 'FAILED':
      return 'FAILED'
    case 'READY':
      return action.contentSource === 'USER' ? 'READY_USER' : 'READY_AI'
    default:
      // 단계가 시작되기 전에 미리 승인하면 초안을 받지 못한다. 승인 전에 알 수 있게 한 줄 남긴다.
      return stepState === 'TODO' && action.status === 'PENDING' ? 'UPCOMING' : 'NONE'
  }
}

// 초안은 응답이 끝난 뒤 서버에서 따로 만들어져 화면이 소식을 받지 못한다.
// 쓰는 중인 Action이 있는 동안만 다시 조회하고, 없으면 멈춘다(운영 상황 2.5초와 같은 방식).
export const DRAFT_POLL_MS = 3000

export function draftPollInterval(actions: EventAction[] | undefined): number | false {
  return actions?.some((action) => action.contentStatus === 'DRAFTING') ? DRAFT_POLL_MS : false
}

// 본문의 [ ] 안 글자. 서버의 contentUnknowns와 같은 규칙이다(#333).
// 모달에서는 입력하는 글에서 바로 뽑아, 채운 자리는 그 자리에서 목록에서 빠진다.
const BLANK = /\[([^[\]\n]+)\]/g

export function blanksIn(text: string): string[] {
  const found = Array.from(text.matchAll(BLANK), (match) => match[1].trim()).filter(Boolean)
  return [...new Set(found)]
}

// 미리보기에서 빈 자리를 따로 칠하려고 글을 나눈다
export function splitBlanks(text: string): Array<{ text: string; blank: boolean }> {
  const parts: Array<{ text: string; blank: boolean }> = []
  let last = 0
  for (const match of text.matchAll(BLANK)) {
    const at = match.index ?? 0
    if (at > last) parts.push({ text: text.slice(last, at), blank: false })
    parts.push({ text: match[0], blank: true })
    last = at + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), blank: false })
  return parts
}

export function blanksLine(blanks: string[] | undefined): string | undefined {
  return blanks && blanks.length > 0 ? `비워 둔 곳: ${blanks.join(', ')}` : undefined
}

// ── 모달에서 본문 고치기 ──
// 고치기 시작한 때의 version을 함께 기억한다. 그사이 초안이 도착하면 저장이 409가 되어
// 운영진이 모르는 채로 토리 초안을 덮어쓰지 않는다.
export interface ContentEdit {
  actionId: string
  text: string
  baseVersion: number | undefined
}

// 입력칸에 보일 글. 고치기 시작했으면 다시 조회한 값으로 덮지 않는다.
export function editorText(action: EventAction, edit: ContentEdit | null): string {
  return edit && edit.actionId === action.id ? edit.text : (action.content ?? '')
}

export function startEdit(action: EventAction, edit: ContentEdit | null, text: string): ContentEdit {
  const base = edit && edit.actionId === action.id ? edit.baseVersion : action.version
  return { actionId: action.id, text, baseVersion: base }
}

export function isDirty(action: EventAction, edit: ContentEdit | null): boolean {
  return !!edit && edit.actionId === action.id && edit.text !== (action.content ?? '')
}

// 빈 글은 서버가 422로 막는다. 고친 것이 없으면 저장할 이유가 없다.
export function canSave(action: EventAction, edit: ContentEdit | null): boolean {
  return isDirty(action, edit) && editorText(action, edit).trim() !== ''
}

// ── 서버 응답 읽기 ──
export type ActionOutcome = 'ok' | 'conflict' | 'failed'

export function errorCode(error: unknown): string | undefined {
  if (error && typeof error === 'object' && 'code' in error && typeof error.code === 'string')
    return error.code
  return undefined
}

// 저장·승인: 보고 있던 사이 내용이 바뀌었으면(초안 도착 등) 다시 불러와 고르게 한다
export function outcomeOf(error: unknown): Exclude<ActionOutcome, 'ok'> {
  return errorCode(error) === 'VERSION_CONFLICT' ? 'conflict' : 'failed'
}

// 「다시 받기」의 409는 어느 쪽이든 최신 상태를 다시 불러와 보여 주면 된다
export function redraftNotice(error: unknown): { title: string; desc: string } | undefined {
  const code = errorCode(error)
  if (code === 'VERSION_CONFLICT' || code === 'DRAFT_NOT_ALLOWED')
    return { title: '다른 변경이 있어요', desc: '최신 내용을 다시 불러왔어요. 확인한 뒤 다시 눌러 주세요.' }
  return undefined
}
