import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

// --- 단계 수정 · 행사 시작 (#213 으로 서버 경로가 생기기 전까지 로컬) ----------

export function codesFromSteps(steps: S['PlannedStepOut'][]): string[] {
  return steps.map((step) => step.code)
}

export function usePlanSteps(eventId: string | null) {
  return useQuery({
    queryKey: ['planning', 'steps', eventId],
    queryFn: () => planningApi.steps(eventId!),
    enabled: !!eventId,
    retry: false,
  })
}

export function useSavePlanSteps(eventId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (codes: string[]) => planningApi.saveSteps(eventId!, codes),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['planning'] }),
  })
}

export function useStartEvent(eventId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => planningApi.start(eventId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['planning'] }),
  })
}

// 저장한 단계 구성을 서버 응답 위에 덮어 보여준다. 뺀 단계는 빼고, 순서도
// 저장한 대로 다시 세운다. 서버가 구성을 받기 시작하면(#213 3단계) 사라진다.
export function applyLocalCodes(
  steps: S['PlannedStepOut'][],
  codes: string[] | null,
): S['PlannedStepOut'][] {
  if (!codes) return steps
  const byCode = new Map<string, S['PlannedStepOut']>(steps.map((step) => [step.code, step]))
  return codes
    .map((code) => byCode.get(code))
    .filter((step): step is S['PlannedStepOut'] => step !== undefined)
    .map((step, index) => ({ ...step, stepOrder: index + 1 }))
}

// 세부 수정 저장 (#106 ④). 일정은 Step, 나머지는 Action 으로 간다.
// 바뀐 것만 보낸다 — PATCH 가 보낸 밭만 덮으므로 건드리지 않은 값은 그대로 남는다.
export function useSaveStepDetail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      step,
      draft,
    }: {
      step: S['PlannedStepOut']
      draft: {
        startsAt: string | null
        deadline: string | null
        actions: Record<
          string,
          { title: string; amount: number | null; payload: S['ActionPayloadOut'] }
        >
      }
    }) => {
      if (draft.startsAt !== step.startsAt || draft.deadline !== step.deadline) {
        await planningApi.updateStep(step.id, {
          startsAt: draft.startsAt,
          deadline: draft.deadline,
        })
      }
      for (const action of step.actions) {
        const next = draft.actions[action.id]
        if (!next) continue
        const changed =
          next.title !== action.title ||
          next.amount !== action.amount ||
          JSON.stringify(next.payload) !== JSON.stringify(action.payload)
        if (changed) {
          await planningApi.updateAction(action.id, {
            title: next.title,
            amount: next.amount,
            payload: next.payload,
          })
        }
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['planning'] }),
  })
}
