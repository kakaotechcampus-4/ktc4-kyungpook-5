import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { planningApi } from './api'
import type { ChatMessage, PlanFacts } from './types'
import { FIRST_MESSAGE } from './mock'
import { ApiError } from '@/shared/api/types'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
type Draft = S['PlanDraftOut']
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
    const topic =
      field === 'startDate' ? 'dates' : field.replace(/[A-Z]/g, (x) => `_${x.toLowerCase()}`)
    if ((value === null || value === undefined) && draft.deferredTopics.includes(topic)) {
      result[label] = { status: '나중에' }
    } else if (value !== null && value !== undefined)
      result[label] = {
        status: meta?.status === 'tentative' ? '잠정' : '확정',
        value: String(value),
        quote: meta?.evidenceQuote,
      }
  }
  return result
}
export function usePlanningDrafts(clubId: string | null, userId: string | undefined) {
  return useQuery({
    queryKey: ['planning', 'drafts', userId, clubId],
    queryFn: () => planningApi.drafts(clubId!),
    enabled: !!clubId,
    retry: false,
  })
}
export function usePlanningChat(
  clubId: string | null,
  selectedId: string | null,
  userId: string | undefined,
  onCreated: (id: string, failedText?: string) => void,
) {
  const queryClient = useQueryClient()
  const [view, setView] = useState<S['PlanViewOut'] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const locked = useRef(false)
  const snapshot = useQuery({
    queryKey: ['planning', 'snapshot', userId, clubId, selectedId],
    enabled: !!clubId && !!selectedId,
    retry: false,
    queryFn: async () => {
      const [screen, messages, steps] = await Promise.all([
        planningApi.get(selectedId!),
        planningApi.messages(selectedId!),
        planningApi.steps(selectedId!),
      ])
      return { screen, messages, steps }
    },
  })
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: ['planning', 'snapshot', userId, clubId, selectedId],
    })
  const storedMessages: ChatMessage[] = (snapshot.data?.messages ?? []).map((m) => ({
    id: m.id,
    from: m.role === 'USER' ? '나' : '토리',
    text: m.content,
  }))
  const messages = [FIRST_MESSAGE, ...storedMessages]
  const screen = snapshot.data?.screen
  const currentView = view && view.baseRevision >= (screen?.baseRevision ?? 0) ? view : null
  const revision = currentView?.baseRevision ?? screen?.baseRevision ?? 0
  const facts = toFacts(
    currentView?.draft ??
      snapshot.data?.screen.draft ?? {
        conditions: {
          title: null,
          eventType: null,
          headcount: null,
          feePerPerson: null,
          startDate: null,
          endDate: null,
          location: null,
          budgetTotal: null,
        },
        conditionMeta: {},
        deferredTopics: [],
      },
  )
  const send = async (text: string) => {
    if (locked.current || (selectedId && !snapshot.data)) return false
    if (!clubId) {
      setError('로그인하고 소속을 선택해 주세요.')
      return false
    }
    locked.current = true
    setBusy(true)
    setError('')
    let eventId = selectedId
    const id = crypto.randomUUID()
    let succeeded = false
    try {
      if (!eventId) eventId = (await planningApi.create(clubId)).id
      const result = await planningApi.chat(eventId, {
        messageId: id,
        message: text,
        baseRevision: revision,
      })
      setView(result)
      succeeded = true
      if (selectedId) {
        const updated = await snapshot.refetch()
        if (updated.isError)
          setError('답변은 처리됐지만 대화 이력을 불러오지 못했어요. 다시 확인해 주세요.')
        else if (!result.reply) setError('답변을 받지 못했어요. 계획 상태를 확인해 주세요.')
      }
      return true
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === 'VERSION_CONFLICT'
          ? '다른 변경이 있어요. 계획을 다시 불러온 뒤 확인해 주세요.'
          : cause instanceof ApiError && cause.code === 'AI_UNAVAILABLE'
            ? '답변 서비스를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.'
            : '계획 답변을 확인하지 못했어요. 요청이 반영됐을 수 있으니 다시 보내기 전에 확인해 주세요.',
      )
      return false
    } finally {
      locked.current = false
      setBusy(false)
      void queryClient.invalidateQueries({ queryKey: ['planning', 'drafts', userId, clubId] })
      if (eventId && !selectedId) onCreated(eventId, succeeded ? undefined : text)
    }
  }
  const generate = async () => {
    if (!selectedId || !snapshot.data || locked.current) return
    locked.current = true
    setBusy(true)
    setError('')
    try {
      const result = await planningApi.generate(selectedId, {
        baseRevision: revision,
        useCurrentConditions: false,
      })
      setView(result)
      await refresh()
      if (result.generationResult?.status !== 'generated')
        setError(result.reply || '계획을 생성하지 못했어요. 조건을 확인해 주세요.')
    } catch {
      setError('계획 생성 결과를 확인하지 못했어요. 다시 불러와 저장 상태를 확인해 주세요.')
    } finally {
      locked.current = false
      setBusy(false)
    }
  }
  return { messages, facts, busy, error, send, generate, snapshot, view: currentView, revision }
}
