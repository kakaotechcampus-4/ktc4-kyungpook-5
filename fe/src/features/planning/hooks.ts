import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { planningApi } from './api'
import { STEP_CATALOGUE } from './catalogue'
import type { ChatMessage, PlanFacts, PlanStep, StepActor } from './types'
import { FIRST_MESSAGE } from './mock'
import { ApiError } from '@/shared/api/types'
import type { components } from '@/shared/api/schema'
import { formatCurrency, formatDateRange, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL, STEP_ACTOR_LABEL } from '@/shared/lib/labels'

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
    // 만들어졌으면 true. 화면이 이걸 보고 2단계로 넘어간다.
    if (!selectedId || !snapshot.data || locked.current) return false
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
      const generated = result.generationResult?.status === 'generated'
      if (!generated) setError(result.reply || '계획을 생성하지 못했어요. 조건을 확인해 주세요.')
      return generated
    } catch {
      setError('계획 생성 결과를 확인하지 못했어요. 다시 불러와 저장 상태를 확인해 주세요.')
      return false
    } finally {
      locked.current = false
      setBusy(false)
    }
  }
  return { messages, facts, busy, error, send, generate, snapshot, view: currentView, revision }
}

// --- 단계 수정 · 행사 시작 (#213) ----------

export function codesFromSteps(steps: S['PlannedStepOut'][]): string[] {
  return steps.map((step) => step.code)
}

// 서버 단계 → P2 흐름 한 줄(StepFlow). 문구는 labels.ts의 표로 바꾼다.
// ponytail: 묶음(phase)이 PlannedStepOut에 없어 FE 카탈로그에서 찾는다. BE가 phase를 주면 그걸 쓴다.
export function toPlanSteps(steps: S['PlannedStepOut'][]): PlanStep[] {
  return steps.map((step) => {
    const at = step.deadline ?? step.startsAt
    const types = [...new Set(step.actions.map((a) => ACTION_TYPE_LABEL[a.type] ?? a.type))]
    return {
      id: step.id,
      // 모르는 코드는 마지막 묶음에 둔다. 묶음에서 빠지면 화면에서 단계가 조용히 사라진다.
      phase: STEP_CATALOGUE.find((c) => c.code === step.code)?.phase ?? '행사 진행 · 마무리',
      name: step.name,
      actor: (STEP_ACTOR_LABEL[step.actor] ?? '직접 수행') as StepActor,
      actionLabel: types.join(' · ') || undefined,
      date: at ? formatMonthDay(at) : '미정',
      desc: step.actions.find((a) => a.subtitle)?.subtitle ?? '',
      editable: step.editable,
    }
  })
}

// P2 머리 한 줄 "2026 봄 MT · 32명 · 예산 2,000,000원 · 3/21 – 3/22". 정하지 않은 건 뺀다.
export function planMetaLine(conditions: S['PlanConditionsOut']): string {
  return [
    conditions.title,
    conditions.headcount != null && `${conditions.headcount}명`,
    conditions.budgetTotal != null && `예산 ${formatCurrency(conditions.budgetTotal)}`,
    conditions.startDate && formatDateRange(conditions.startDate, conditions.endDate),
  ]
    .filter(Boolean)
    .join(' · ')
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
            // 조회에서 받은 version을 그대로 돌려보낸다. 그사이 내용이 바뀌었으면
            // 서버가 409로 거절하고 다시 불러오게 한다.
            expectedVersion: action.version,
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
