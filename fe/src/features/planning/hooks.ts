import { useRef, useState } from 'react'
import {
  queryOptions,
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { planningApi } from './api'
import { PartialPlanSaveError } from './errors'
import type { ChatMessage, PlanFacts } from './types'
import type { PlanStreamHandlers } from './stream'
import {
  planningSnapshotKey,
  useGenerationRequest,
  type RequestSettled,
} from './useGenerationRequest'
import { FIRST_MESSAGE } from './mock'
import { planningRecordHistory } from './recordReferences'
import {
  attachReceipts,
  dropSkipped,
  finishedLines,
  failedLines,
  LINE_EXIT_MS,
  upsertProgress,
  type TurnLine,
  type TurnReceipt,
} from './turn'
import { changedFacts, type FactFlash } from './factFlash'
import { ApiError } from '@/shared/api/types'
import { formatCurrency, formatDateRange } from '@/shared/lib/format'
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
const metaOf = (draft: Draft, field: string) =>
  draft.conditionMeta[field] ??
  draft.conditionMeta[field.replace(/[A-Z]/g, (x) => `_${x.toLowerCase()}`)]
// 「일정」 칸은 시작일과 종료일을 함께 보인다(#300). "12/5 – 12/6", 하루면 "12/5", 종료일만 있으면 "~ 12/6".
function schedule(draft: Draft) {
  const { startDate, endDate } = draft.conditions
  if (!startDate && !endDate) return null
  return startDate
    ? formatDateRange(startDate, endDate ?? null)
    : `~ ${formatDateRange(endDate!, null)}`
}
// 조건 값은 패널과 답변에 표시하고 진행 줄은 항목 이름만 적는다(#302).
//   headcount 35 → "35명", feePerPerson 0 → "무료", 20000 → "1인 20,000원", eventType WELCOME → "개총·신환회"
const EVENT_TYPES: Record<string, string> = {
  MT: 'MT',
  WELCOME: '개총·신환회',
  PICNIC: '피크닉',
  ACADEMIC: '학술행사',
  WORKSHOP: '워크샵',
  ETC: '기타',
}
function shown(field: (typeof fields)[number][0], value: string | number): string {
  if (field === 'headcount') return `${Number(value).toLocaleString('ko-KR')}명`
  if (field === 'feePerPerson')
    return Number(value) === 0 ? '무료' : `1인 ${formatCurrency(Number(value))}`
  if (field === 'eventType') return EVENT_TYPES[value] ?? String(value)
  return String(value)
}
export function toFacts(draft: Draft): PlanFacts {
  const result: PlanFacts = {}
  for (const [field, label] of fields) {
    const value = field === 'startDate' ? schedule(draft) : draft.conditions[field]
    // 일정은 시작일·종료일 중 하나라도 잠정이면 잠정이다.
    const meta =
      field === 'startDate'
        ? ([metaOf(draft, 'startDate'), metaOf(draft, 'endDate')].find(
            (m) => m?.status === 'tentative',
          ) ?? metaOf(draft, 'startDate'))
        : metaOf(draft, field)
    const topic =
      field === 'startDate' ? 'dates' : field.replace(/[A-Z]/g, (x) => `_${x.toLowerCase()}`)
    if ((value === null || value === undefined) && draft.deferredTopics.includes(topic)) {
      result[label] = { status: '나중에' }
    } else if (value !== null && value !== undefined)
      result[label] = {
        status: meta?.status === 'tentative' ? '잠정' : '확정',
        value: shown(field, value),
        quote: meta?.evidenceQuote,
      }
  }
  return result
}
// 대화 화면이 쓰는 저장 상태 묶음(조건·대화·단계). 새 계획을 만든 직후 미리 받아 둘 때도
// 같은 키·같은 요청을 써야 화면이 넘어가자마자 이 값을 그대로 쓴다.
function snapshotQuery(userId: string | undefined, clubId: string | null, eventId: string | null) {
  return queryOptions({
    queryKey: planningSnapshotKey(userId, clubId, eventId),
    queryFn: async () => {
      const [screen, messages, steps] = await Promise.all([
        planningApi.get(eventId!),
        planningApi.messages(eventId!),
        planningApi.steps(eventId!),
      ])
      return { screen, messages, steps }
    },
    retry: false,
  })
}
function receiptsKey(userId: string | undefined, clubId: string | null, eventId: string | null) {
  return ['planning', 'receipts', userId, clubId, eventId]
}
// 조건 패널의 바뀐 칸 강조. 새 계획은 첫 답변 뒤 화면이 새 주소로 넘어가며 패널이 새로 그려지므로
// 작업 줄처럼 화면 상태가 아니라 계획별 캐시에 둔다.
function flashKey(userId: string | undefined, clubId: string | null, eventId: string | null) {
  return ['planning', 'fact-flash', userId, clubId, eventId]
}
export function usePlanningDrafts(clubId: string | null, userId: string | undefined) {
  return useQuery({
    queryKey: ['planning', 'drafts', userId, clubId],
    queryFn: () => planningApi.drafts(clubId!),
    enabled: !!clubId,
    retry: false,
  })
}
function generationFailureText(result: S['PlanViewOut']): string {
  return (
    (result.generationResult?.status === 'needs_clarification'
      ? '초안을 만들기 전에 확인할 내용이 있어요. '
      : '초안을 완성하지 못했어요. ') +
    (result.generationResult?.reason || result.reply || '조건을 확인해 주세요.')
  )
}

export function usePlanningChat(
  clubId: string | null,
  selectedId: string | null,
  userId: string | undefined,
  onCreated: (id: string, failedText?: string) => void,
  onGenerated: (eventId: string, count: number, key: string) => void,
  prepareCreated?: (eventId: string) => Promise<unknown>,
) {
  const queryClient = useQueryClient()
  // 끊긴 요청의 결과를 조회로 확인했을 때(#342). 저장됐으면 정상 응답처럼 보여 주고,
  // 저장되지 않았으면 다시 보내 달라고 안내한다. 실패로 표시해 둔 진행 줄은 지운다.
  const onSettled = ({ result, saved, text }: RequestSettled) => {
    queryClient.removeQueries({ queryKey: failureKey(selectedId), exact: true })
    clearPending()
    setSettled(saved ? 'saved' : 'not_saved')
    setRetryText(text ?? '')
    if (result) setView(result)
    const failure =
      result?.generationResult && result.generationResult.status !== 'generated'
        ? result.generationResult
        : null
    setGenerationFailure(failure)
    setError(
      !saved
        ? '연결이 끊긴 요청은 처리되지 않았어요. 다시 보내 주세요.'
        : result && failure
          ? generationFailureText(result)
          : '',
    )
  }
  const generation = useGenerationRequest(userId, clubId, selectedId, onGenerated, onSettled)
  // 끊긴 요청을 조회로 확인한 결과. 새 계획의 첫 메시지가 끊긴 경우 화면의 "결과를 확인해 주세요"
  // 안내를 저장 확인 뒤에 지우는 데 쓴다.
  const [settled, setSettled] = useState<'saved' | 'not_saved' | null>(null)
  const [retryText, setRetryText] = useState('')
  const [temporaryDraft, setTemporaryDraft] = useState<Draft | null>(null)
  const temporaryDraftRef = useRef<Draft | null>(null)
  const streamEventId = useRef(selectedId)
  // react-query의 구독 알림을 기다리지 않고 진행 줄과 같은 렌더에서 강조한다.
  const [localFlash, setLocalFlash] = useState<FactFlash | null | undefined>(undefined)
  const updateFlash = (value: FactFlash | null) => {
    setLocalFlash(value)
    queryClient.setQueryData(flashKey(userId, clubId, streamEventId.current), value)
  }
  const failureKey = (id: string | null) => ['planning', 'failed-turn', userId, clubId, id]
  const [view, setView] = useState<S['PlanViewOut'] | null>(null)
  // 채팅 답변 대기와 버튼 초안 생성 대기를 나눈다. 하나로 두면 채팅만 보내도
  // 생성 버튼이 "초안을 만드는 중…"이 된다(#290). 둘 중 하나라도 진행 중이면 입력은 잠근다.
  const [sending, setSending] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [generationFailure, setGenerationFailure] = useState<S['GenerationResultOut'] | null>(null)
  // 스트림으로 받는 동안만 보이는 임시 표시(#285). done 뒤 저장된 대화로 바뀌면 지운다.
  const [progress, setProgress] = useState<TurnLine[]>(
    () => queryClient.getQueryData<TurnLine[]>(failureKey(selectedId)) ?? [],
  )
  const [pendingText, setPendingText] = useState('')
  const [pendingReply, setPendingReply] = useState('')
  const [notice, setNotice] = useState('')
  // 보낼 때 저장돼 있던 대화 수. 다시 불러온 대화가 이보다 많으면 이번 턴이 저장된 것이다.
  const [pendingBase, setPendingBase] = useState<number | null>(null)
  const locked = useRef(false)
  // 이번 턴의 작업 줄. 답변이 끝나면 화면 상태가 아니라 이 값으로 저장할 작업 줄을 정한다.
  const turnLines = useRef<TurnLine[]>([])
  const clearPending = () => {
    setPendingBase(null)
    turnLines.current = []
    setProgress([])
    setPendingText('')
    setPendingReply('')
    setNotice('')
  }
  const handlers: PlanStreamHandlers = {
    // 같은 작업의 진행 줄은 제자리에서 결과 줄로 바꾼다. 이번 턴의 줄은 모두 남긴다(#290).
    onProgress: (event) => {
      generation.progress(event)
      turnLines.current = upsertProgress(turnLines.current, event)
      setProgress(turnLines.current)
      if (
        event.kind === 'condition_applied' &&
        event.status === 'completed' &&
        event.conditionDraft
      ) {
        const next = event.conditionDraft
        const keys = changedFacts(toFacts(temporaryDraftRef.current ?? savedDraft), toFacts(next))
        temporaryDraftRef.current = next
        setTemporaryDraft(next)
        if (keys.length) updateFlash({ at: Date.now(), keys })
      }
    },
    onReply: (text) => {
      setPendingReply(text)
      // 답변이 시작되면 다시 시도되지 않은 조건 줄(거절·같은 값)이 사라지는 움직임
      // (PlanChat의 line-out)을 보인 뒤 목록에서 뺀다. 이유는 이제 나오는 답변이 설명한다.
      if (text && turnLines.current.some((line) => line.status === 'skipped'))
        setTimeout(() => {
          turnLines.current = dropSkipped(turnLines.current)
          setProgress(turnLines.current)
        }, LINE_EXIT_MS)
    },
    onReconnect: () => {
      // 서버는 연결이 끊겨도 저장을 계속한다. 마지막 검증 초안과 줄을 유지해
      // 재확인 실패 시 성공 줄도 실패로 바꾸고 패널을 함께 복구할 수 있게 한다.
      setPendingReply('')
      setNotice('연결이 끊겨 처리 결과를 확인하지 못했어요.')
    },
  }
  const snapshot = useQuery({
    ...snapshotQuery(userId, clubId, selectedId),
    enabled: !!clubId && !!selectedId,
    // 서버가 검토 중이면 결과가 나올 때까지 짧게 다시 불러온다.
    refetchInterval: (q) => (q.state.data?.screen.review?.status === 'REVIEWING' ? 2000 : false),
  })
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: snapshotQuery(userId, clubId, selectedId).queryKey })
  // 이번 화면에서 끝난 턴의 작업 줄. 새 계획은 첫 답변 뒤 대화 영역이 새로 그려지므로
  // 화면 상태가 아니라 계획별 캐시에 둔다. 서버에 저장하지 않아 새로고침하면 사라진다.
  const receipts = useQuery({
    queryKey: receiptsKey(userId, clubId, selectedId),
    queryFn: () => [] as TurnReceipt[],
    enabled: !!selectedId,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  const storedMessages: ChatMessage[] = attachReceipts(
    (snapshot.data?.messages ?? []).map((m) => ({
      id: m.id,
      from: m.role === 'USER' ? '나' : '토리',
      text: m.content,
    })),
    receipts.data ?? [],
  )
  const messages = [FIRST_MESSAGE, ...storedMessages]
  const flash = useQuery({
    queryKey: flashKey(userId, clubId, selectedId),
    queryFn: () => null as FactFlash | null,
    enabled: !!selectedId,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  // 저장된 대화에 이번 턴이 들어오면 임시 표시는 같은 화면 갱신에서 숨긴다.
  // 임시 표시를 지우는 일과 다시 불러온 대화를 그리는 일이 따로 일어나도 두 번 보이지 않는다.
  const turnSaved = pendingBase !== null && storedMessages.length > pendingBase
  const screen = snapshot.data?.screen
  const currentView = view && view.baseRevision >= (screen?.baseRevision ?? 0) ? view : null
  const revision = currentView?.baseRevision ?? screen?.baseRevision ?? 0
  const savedDraft = currentView?.draft ??
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
    }
  const facts = toFacts(temporaryDraft ?? savedDraft)
  const send = async (text: string) => {
    if (locked.current || generation.blocked || (selectedId && !snapshot.data)) return false
    if (!clubId) {
      setError('로그인하고 소속을 선택해 주세요.')
      return false
    }
    locked.current = true
    setSending(true)
    setError('')
    setGenerationFailure(null)
    clearPending()
    queryClient.removeQueries({ queryKey: failureKey(selectedId), exact: true })
    temporaryDraftRef.current = null
    setTemporaryDraft(null)
    updateFlash(null)
    setPendingText(text)
    const base = storedMessages.length
    setPendingBase(base)
    // 보내기 전 대화 이력 사용량. 실패 원인을 추정할 때 쓴다(#329).
    const usage = currentView?.historyUsage ?? screen?.historyUsage
    let eventId = selectedId
    const id = crypto.randomUUID()
    let succeeded = false
    let generated = false
    try {
      if (!eventId) eventId = (await planningApi.create(clubId)).id
      streamEventId.current = eventId
      const request = await generation.begin(
        eventId,
        'chat',
        { messageId: id, message: text, baseRevision: revision },
        savedDraft,
      )
      // messageId를 멱등키와 탭 기록에 함께 쓴다. 연결 단절 때는 자동 재전송하지 않는다.
      const result = await planningApi.chatStream(
        eventId,
        request.body as S['PlanChatIn'],
        request.key,
        handlers,
      )
      setView(result)
      succeeded = true
      // 마지막으로 보인 임시 값과 저장 결과가 다를 때만 그 칸을 다시 강조한다.
      // 완료 이벤트가 없는 재연결/이전 서버도 저장 결과와 비교해 정상 표시한다.
      const keys = changedFacts(
        toFacts(temporaryDraftRef.current ?? savedDraft),
        toFacts(result.draft),
      )
      temporaryDraftRef.current = null
      setTemporaryDraft(null)
      if (keys.length) updateFlash({ at: Date.now(), keys })
      // 저장된 대화를 다시 불러오기 전에 작업 줄을 먼저 넣어 둔다. 그래야 임시 표시가
      // 저장된 답변으로 바뀌는 같은 화면 갱신에서 작업 줄이 답변 위에 그대로 남는다.
      const lines = finishedLines(turnLines.current)
      if (lines.length)
        queryClient.setQueryData<TurnReceipt[]>(
          receiptsKey(userId, clubId, eventId),
          (old = []) => [...old, { base, lines }],
        )
      if (result.generationResult?.status === 'generated') {
        generated = true
        await generation.finish(result)
        return true
      }
      await generation.finish(result)
      if (result.generationResult) {
        setGenerationFailure(result.generationResult)
        setError(generationFailureText(result))
      }
      if (!selectedId) {
        // 새 계획: 끝나면 화면이 이 계획 주소로 넘어가며 대화 영역을 새로 그린다.
        // 대화와 화면 진입에 필요한 행사 상세를 함께 준비한다. 대화만 준비하면
        // 상세 조회를 기다리는 동안 전체 대화가 "불러오는 중" 카드로 바뀐다.
        // 실패해도 넘어간 화면이 직접 다시 불러오므로 여기서는 오류로 보지 않는다.
        await Promise.allSettled([
          queryClient.fetchQuery(snapshotQuery(userId, clubId, eventId)),
          prepareCreated?.(eventId),
        ])
      } else {
        const updated = await snapshot.refetch()
        if (updated.isError)
          setError('답변은 처리됐지만 대화 이력을 불러오지 못했어요. 다시 확인해 주세요.')
        else if (!result.reply) setError('답변을 받지 못했어요. 계획 상태를 확인해 주세요.')
      }
      return true
    } catch (cause) {
      generation.fail(cause)
      // 성공처럼 보이던 임시 값과 강조를 버리고, 저장된 패널로 돌아간다.
      temporaryDraftRef.current = null
      setTemporaryDraft(null)
      updateFlash(null)
      // 이력 한도로 저장 단계에서 거절되면 아무것도 반영되지 않는다(#329). 오류 코드는 다른 계획 상태
      // 오류와 같아서, 보내기 전 사용량이 한도 근처였는지로 원인을 추정한다.
      const historyLimit =
        cause instanceof ApiError && cause.code === 'PLANNING_STATE_CONFLICT' && !!usage?.nearLimit
      const failed = failedLines(turnLines.current, historyLimit)
      turnLines.current = failed
      setProgress(failed)
      setPendingBase(null)
      setPendingReply('')
      if (eventId) queryClient.setQueryData(failureKey(eventId), failed)
      setError(
        historyLimit
          ? '대화가 길어져 이번 요청을 저장하지 못했어요. 반영된 내용은 없어요.'
          : cause instanceof ApiError && cause.code === 'VERSION_CONFLICT'
            ? '다른 변경이 있어요. 계획을 다시 불러온 뒤 확인해 주세요.'
            : cause instanceof ApiError && cause.code === 'AI_UNAVAILABLE'
              ? '답변 서비스를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.'
              : '계획 답변을 확인하지 못했어요. 요청이 반영됐을 수 있으니 다시 보내기 전에 확인해 주세요.',
      )
      // 흘려 받은 답변·진행 표시는 저장되지 않았을 수 있다. 저장된 상태를 다시 불러온다.
      if (selectedId) void snapshot.refetch()
      return false
    } finally {
      locked.current = false
      void queryClient.invalidateQueries({ queryKey: ['planning', 'drafts', userId, clubId] })
      if (eventId && !selectedId && !generated && generation.isCurrent()) {
        // 새 계획은 이 대화 영역이 새 주소의 영역으로 바뀐다. 주소 이동은 다음 화면 갱신에서
        // 반영되므로, 여기서 임시 표시를 먼저 지우면 그 사이 한 번 빈 대화가 보인다.
        // 바뀔 때까지 그대로 두고 새 영역이 저장된 대화를 그린다.
        onCreated(eventId, succeeded ? undefined : text)
      } else {
        if (succeeded) clearPending()
        setSending(false)
      }
    }
  }
  const generate = async () => {
    if (!selectedId || !snapshot.data || locked.current || generation.blocked) return
    locked.current = true
    setGenerating(true)
    setError('')
    setGenerationFailure(null)
    clearPending()
    try {
      const request = await generation.begin(
        selectedId,
        'button',
        { baseRevision: revision, useCurrentConditions: false },
        savedDraft,
      )
      const result = await planningApi.generateStream(
        selectedId,
        request.body as S['PlanGenerateIn'],
        request.key,
        handlers,
      )
      setView(result)
      await generation.finish(result)
      if (result.generationResult?.status !== 'generated') {
        setGenerationFailure(result.generationResult)
        await refresh()
        setError(generationFailureText(result))
      }
    } catch (cause) {
      const unknown = generation.fail(cause)
      setError(
        unknown
          ? ''
          : cause instanceof ApiError && cause.code === 'VERSION_CONFLICT'
            ? '생성한 초안을 저장하지 못했어요. 다른 변경이 있어요. 저장된 계획을 다시 확인해 주세요.'
            : cause instanceof ApiError && cause.code === 'PLAN_EDITED_CONFLICT'
              ? '직접 수정한 계획이 있어요. 기존 초안을 확인해 주세요.'
              : '생성 요청을 처리하지 못했어요. 저장된 계획과 브라우저의 임시 저장 기능을 확인해 주세요.',
      )
      void refresh()
    } finally {
      clearPending()
      locked.current = false
      setGenerating(false)
    }
  }
  const recordHistory = planningRecordHistory(screen, currentView)
  return {
    messages,
    facts,
    factFlash: localFlash === undefined ? (flash.data ?? null) : localFlash,
    busy: sending || generating || generation.blocked || !!generation.flow,
    // 이 화면에서 스트림을 받는 중인가. 결과를 확인하는 중인 행사가 있어도 다른 계획으로는
    // 옮길 수 있게, 계획 선택 잠금에는 이 값만 쓴다(#342).
    streaming: sending || generating,
    settled,
    // 입력창을 다시 그릴 때 넣을 문장. 저장되지 않은 채팅이면 그 문장을 되돌린다.
    retryText,
    generationFlow: generation.flow,
    generationFailure,
    reloadGenerated: generation.load,
    viewCurrentPlan: generation.viewCurrent,
    generating,
    error,
    send,
    generate,
    snapshot,
    view: currentView,
    revision,
    recordHistory,
    progress: turnSaved ? [] : progress,
    pendingText: turnSaved ? '' : pendingText,
    pendingReply: turnSaved ? '' : pendingReply,
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
