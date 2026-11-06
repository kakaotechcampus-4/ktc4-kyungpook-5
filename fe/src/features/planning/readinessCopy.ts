// 초안을 만들 수 없을 때 조건 카드 아래에 보이는 안내.
// 서버가 준 이유 가운데 조건 목록의 한 줄과 바로 이어지는 것은 그 줄에 「필요해요」로 표시하고,
// 문장에는 항목 이름만 한 번 모아 쓴다. 이유마다 문장을 이어 붙이면 같은 말이 반복된다.
import type { PlanFactKey } from './types'

// 목록 순서(PLAN_FACT_KEYS)대로 나열한다. 문장 속 이름은 목록 이름보다 짧게 쓴다.
const FACT_REASONS: { reason: string; key: PlanFactKey; word: string; deferrable: boolean }[] = [
  { reason: 'event_type_missing', key: '종류', word: '행사 종류', deferrable: false },
  { reason: 'headcount_unanswered', key: '예상 인원', word: '인원', deferrable: true },
  { reason: 'dates_unanswered', key: '일정', word: '일정', deferrable: true },
  { reason: 'location_unanswered', key: '장소', word: '장소', deferrable: true },
]

const OTHER_REASONS: Record<string, string> = {
  condition_change_pending: '반영하지 못한 조건 변경을 먼저 확인해 주세요.',
}

// 마지막 글자에 받침이 있으면 「을」, 없으면 「를」.
function objectParticle(word: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? '을' : '를'
}

// 문장은 한 줄씩 따로 보인다. 이어 쓰면 칸이 좁아 다음 문장이 줄 가운데서 시작한다.
export function readinessCopy(reasons: readonly string[]): {
  needed: PlanFactKey[]
  sentences: string[]
  text: string
} {
  const missing = FACT_REASONS.filter(({ reason }) => reasons.includes(reason))
  const sentences: string[] = []
  if (missing.length) {
    const words = missing.map(({ word }) => word).join('·')
    sentences.push(`${words}${objectParticle(words)} 정하면 초안을 만들 수 있어요.`)
    if (missing.some(({ deferrable }) => deferrable))
      sentences.push('아직 모르면 "미정"이라고 답해도 돼요.')
  }
  const known = new Set(FACT_REASONS.map(({ reason }) => reason))
  for (const reason of reasons) {
    if (known.has(reason)) continue
    const sentence = OTHER_REASONS[reason] ?? '추가 정보를 확인해 주세요.'
    if (!sentences.includes(sentence)) sentences.push(sentence)
  }
  if (!sentences.length) sentences.push('대화를 이어서 필요한 정보를 확인해 주세요.')
  return { needed: missing.map(({ key }) => key), sentences, text: sentences.join(' ') }
}
