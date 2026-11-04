import { useRef, useState } from 'react'
import { useIsMutating, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { planningApi } from './api'
import { PartialPlanSaveError } from './errors'
import type { ChatMessage, PlanFacts, PlanProgress } from './types'
import type { PlanStreamHandlers } from './stream'
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
  // 스트림으로 받는 동안만 보이는 임시 표시(#285). done 뒤 저장된 대화로 바뀌면 지운다.
  const [progress, setProgress] = useState<PlanProgress[]>([])
  const [pendingText, setPendingText] = useState('')
  const [pendingReply, setPendingReply] = useState('')
  const [notice, setNotice] = useState('')
  const locked = useRef(false)
  const clearPending = () => {
    setProgress([])
    setPendingText('')
    setPendingReply('')
    setNotice('')
  }
  const handlers: PlanStreamHandlers = {
    // 같은 작업의 진행 줄은 결과 줄로 바꾸고, 현재 단계와 직전 결과 두 줄만 남긴다.
    onProgress: (event) =>
      setProgress((lines) =>
        [...lines.filter((line) => line.operationId !== event.operationId), event].slice(-2),
      ),
    onReply: setPendingReply,
    onReconnect: () => {
      setProgress([])
      setPendingReply('')
      setNotice('연결이 끊겨 처리 결과를 다시 확인하고 있어요…')
    },
  }
  const snapshot = useQuery({
    queryKey: ['planning', 'snapshot', userId, clubId, selectedId],
    enabled: !!clubId && !!selectedId,
    retry: false,
    // 서버가 검토 중이면 결과가 나올 때까지 짧게 다시 불러온다.
    refetchInterval: (q) => (q.state.data?.screen.review?.status === 'REVIEWING' ? 2000 : false),
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
    clearPending()
    setPendingText(text)
    let eventId = selectedId
    const id = crypto.randomUUID()
    let succeeded = false
    try {
      if (!eventId) eventId = (await planningApi.create(clubId)).id
      // messageId를 멱등키로도 쓴다. 끊겨서 다시 보내도 같은 턴이 두 번 처리되지 않는다.
      const result = await planningApi.chatStream(
        eventId,
        { messageId: id, message: text, baseRevision: revision },
        id,
        handlers,
      )
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
      // 흘려 받은 답변·진행 표시는 저장되지 않았을 수 있다. 저장된 상태를 다시 불러온다.
      if (selectedId) void snapshot.refetch()
      return false
    } finally {
      clearPending()
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
    clearPending()
    try {
      const result = await planningApi.generateStream(
        selectedId,
        { baseRevision: revision, useCurrentConditions: false },
        crypto.randomUUID(),
        handlers,
      )
      setView(result)
      await refresh()
      if (result.generationResult?.status !== 'generated')
        setError(result.reply || '계획을 생성하지 못했어요. 조건을 확인해 주세요.')
    } catch {
      setError('계획 생성 결과를 확인하지 못했어요. 다시 불러와 저장 상태를 확인해 주세요.')
      void refresh()
    } finally {
      clearPending()
      locked.current = false
      setBusy(false)
    }
  }
  return {
    messages,
    facts,
    busy,
    error,
    send,
    generate,
    snapshot,
    view: currentView,
    revision,
    progress,
    pendingText,
    pendingReply,
    notice,
  }
}

// --- 단계 수정 · 행사 시작 --------------------------------------------------

export function codesFromSteps(steps: S['PlannedStepOut'][]): string[] {
  return steps.map((step) => step.code)
}

export function usePlanStepsSnapshot(eventId: string | null) {
  return useQuery({
    queryKey: ['planning', 'steps-snapshot', eventId],
    queryFn: () => planningApi.stepsSnapshot(eventId!),
    enabled: !!eventId,
    retry: false,
  })
}

export function useSavePlanSteps(eventId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: { codes: string[]; expectedRevision: number }) =>
      planningApi.saveSteps(eventId!, input.codes, input.expectedRevision),
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

// 저장한 단계 구성을 서버가 반환한 목록에 적용하는 보조 함수.
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
      const stepChanged = draft.startsAt !== step.startsAt || draft.deadline !== step.deadline
      const changedActions = step.actions.filter((action) => {
        const next = draft.actions[action.id]
        return (
          !!next &&
          (next.title !== action.title ||
            next.amount !== action.amount ||
            JSON.stringify(next.payload) !== JSON.stringify(action.payload))
        )
      })
      const totalChanges = (stepChanged ? 1 : 0) + changedActions.length
      const completed: string[] = []
      try {
        if (stepChanged) {
          await planningApi.updateStep(step.id, {
            expectedVersion: step.version,
            startsAt: draft.startsAt,
            deadline: draft.deadline,
          })
          completed.push('일정')
        }
        for (const action of changedActions) {
          const next = draft.actions[action.id]
          await planningApi.updateAction(action.id, {
            expectedVersion: action.version,
            title: next.title,
            amount: next.amount,
            payload: next.payload,
          })
          completed.push(`작업 '${action.title}'`)
        }
      } catch (cause) {
        if (completed.length) {
          throw new PartialPlanSaveError(completed, Math.max(1, totalChanges - completed.length))
        }
        throw cause
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['planning'] }),
  })
}

// 계획 검토 요청 (#177). 무효화는 옵션에 둔다 — 호출한 화면이 먼저 사라져도 실행돼야 한다.
export const reviewMutationKey = (eventId: string) => ['planning', 'review', eventId] as const

export function useRequestPlanReview(eventId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationKey: reviewMutationKey(eventId ?? ''),
    mutationFn: (expectedRevision: number) => planningApi.review(eventId!, expectedRevision),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['planning'] }),
  })
}

// 다른 화면에서 보낸 검토 요청까지 포함해 진행 중인지.
export function useReviewInFlight(eventId: string | null): boolean {
  return useIsMutating({ mutationKey: reviewMutationKey(eventId ?? '') }) > 0
}
