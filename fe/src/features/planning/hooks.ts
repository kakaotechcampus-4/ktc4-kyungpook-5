import { useRef, useState } from 'react'
import { planningApi } from './api'
import type { ChatMessage, PlanFacts } from './types'
import { FIRST_MESSAGE } from './mock'
import { ApiError } from '@/shared/api/types'
import type { components } from '@/shared/api/schema'

type Draft = components['schemas']['PlanDraftOut']
const fields = [
  ['title', '행사 이름'],
  ['eventType', '종류'],
  ['headcount', '예상 인원'],
  ['feePerPerson', '참가비'],
  ['startDate', '일정'],
  ['location', '장소'],
] as const
function toFacts(draft: Draft): PlanFacts {
  const result: PlanFacts = {}
  for (const [field, label] of fields) {
    const value = draft.conditions[field]
    const meta =
      draft.conditionMeta[field] ??
      draft.conditionMeta[field.replace(/[A-Z]/g, (x) => `_${x.toLowerCase()}`)]
    if (value !== null && value !== undefined) {
      result[label] = {
        status: meta?.status === 'tentative' ? '잠정' : '확정',
        value: String(value),
        quote: meta?.evidenceQuote,
      }
    }
  }
  return result
}
export function usePlanningChat(clubId: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([FIRST_MESSAGE])
  const [facts, setFacts] = useState<PlanFacts>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const eventId = useRef<string | null>(null)
  const revision = useRef(0)
  const locked = useRef(false)
  const send = async (text: string) => {
    if (locked.current) return
    if (!clubId) {
      setError('로그인하고 소속을 선택해 주세요.')
      return
    }
    locked.current = true
    setBusy(true)
    setError('')
    const id = crypto.randomUUID()
    setMessages((previous) => [...previous, { id, from: '나', text }])
    try {
      if (!eventId.current) eventId.current = (await planningApi.create(clubId)).id
      const view = await planningApi.chat(eventId.current, {
        messageId: id,
        message: text,
        baseRevision: revision.current,
      })
      revision.current = view.baseRevision
      setFacts(toFacts(view.draft))
      if (view.reply)
        setMessages((previous) => [
          ...previous,
          { id: `${id}-reply`, from: '토리', text: view.reply! },
        ])
      else setError('답변을 받지 못했어요. 잠시 후 다시 시도해 주세요.')
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'VERSION_CONFLICT' && eventId.current) {
        try {
          revision.current = (await planningApi.get(eventId.current)).baseRevision
        } catch {
          /* 다음 시도에서 다시 확인 */
        }
      }
      setError(
        cause instanceof ApiError && cause.code === 'AI_UNAVAILABLE'
          ? '계획 답변 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.'
          : cause instanceof ApiError && cause.code === 'VERSION_CONFLICT'
            ? '계획이 변경되어 최신 상태를 확인했어요. 답변을 다시 보내 주세요.'
            : '계획 답변을 받지 못했어요. 연결과 로그인 상태를 확인하고 다시 시도해 주세요.',
      )
    } finally {
      locked.current = false
      setBusy(false)
    }
  }
  return { messages, facts, busy, error, send }
}
