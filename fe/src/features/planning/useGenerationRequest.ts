import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { planningApi } from './api'
import {
  checksInChat,
  generatedSnapshotStatus,
  parseRequest,
  readRequestText,
  recoveryStep,
  removeRequest,
  subscribeRequest,
  writeRequest,
  type GenerationFlow,
  type PlanningRequest,
} from './generation'
import type { PlanProgress } from './types'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { withViewTransition } from '@/shared/lib/viewTransition'

type S = components['schemas']
export const planningSnapshotKey = (
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
) => ['planning', 'snapshot', userId, clubId, eventId]

export function usePlanningRequestJournal(
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
) {
  const raw = useSyncExternalStore(
    subscribeRequest,
    () => readRequestText(userId, clubId, eventId),
    () => null,
  )
  return { raw, request: parseRequest(raw, userId, clubId, eventId) }
}

// 결과를 모르는 요청을 다시 조회하는 간격. 처리 중이거나 배포로 서버가 잠시 응답하지 않을 때 쓴다.
export const LOOKUP_RETRY_MS = 3000

// 끊긴 요청의 결과를 조회로 확인한 뒤 화면에 알리는 내용(#342).
// result가 있으면 정상 응답을 받은 것처럼 보여 주고, saved가 false면 다시 보내게 안내한다.
export interface RequestSettled {
  result?: S['PlanViewOut']
  saved: boolean
  // 저장되지 않은 채팅의 원래 문장. 입력창에 되돌려 다시 보내기 쉽게 한다.
  text?: string
}

// The chat hook owns the stream. This hook only tracks the request and reads its saved result.
export function useGenerationRequest(
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
  onGenerated: (eventId: string, count: number, key: string) => void,
  onSettled: (settled: RequestSettled) => void = () => {},
) {
  const queryClient = useQueryClient()
  const journal = usePlanningRequestJournal(userId, clubId, eventId)
  const active = useRef<PlanningRequest | null>(null)
  const mounted = useRef(true)
  const [flow, setFlow] = useState<GenerationFlow | null>(null)
  const reading = useRef(false)
  // 생성 화면이 이미 떠 있는가. 처음 띄우는 순간에만 화면 전환 움직임을 준다.
  const visible = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  const show = (phase: GenerationFlow['phase'], request: PlanningRequest) => {
    if (phase === 'load-failed' || phase === 'unconfirmed' || phase === 'changed') {
      request.recovery = phase
      try {
        writeRequest(request)
      } catch {
        /* The earlier journal remains locked. */
      }
    }
    if (mounted.current) setFlow({ phase, draft: request.draft })
  }
  const own = journal.request
  const restoredFlow: GenerationFlow | null =
    own && !active.current
      ? {
          phase:
            own.result?.generationResult?.status === 'generated'
              ? (own.recovery ?? 'load-failed')
              : 'unknown',
          draft: own.draft,
        }
      : null
  const begin = async (
    id: string,
    kind: PlanningRequest['kind'],
    body: PlanningRequest['body'],
    draft: S['PlanDraftOut'],
  ) => {
    if (!userId || !clubId || readRequestText(userId, clubId, id)) throw new Error('REQUEST_LOCKED')
    // 버튼은 누른 순간 생성 화면으로 바뀐다. 오른쪽 조건 카드가 생성 화면으로 이어지게 한다.
    if (kind === 'button' && mounted.current)
      withViewTransition(() => setFlow({ phase: 'requesting', draft }))
    // Read the steps and revision under the server's existing snapshot lock before POST.
    const baseline = await planningApi.stepsSnapshot(id)
    if (!mounted.current) throw new Error('REQUEST_LEFT')
    if (baseline.baseRevision !== body.baseRevision)
      throw new ApiError({
        code: 'VERSION_CONFLICT',
        message: '다른 변경이 있어요. 저장된 계획을 다시 확인해 주세요.',
      })
    const request: PlanningRequest = {
      version: 1,
      userId,
      clubId,
      eventId: id,
      key: kind === 'chat' ? (body as S['PlanChatIn']).messageId : crypto.randomUUID(),
      kind,
      body,
      baseline: {
        baseRevision: baseline.baseRevision,
        planRevision: baseline.planRevision,
        steps: baseline.steps.map(({ id }) => ({ id })),
      },
      draft,
      started: false,
    }
    // Failure to persist stops the first POST as well: reload must never silently unlock it.
    active.current = request
    try {
      writeRequest(request)
    } catch (cause) {
      active.current = null
      throw cause
    }
    return request
  }
  const progress = (event: PlanProgress) => {
    const request = active.current
    if (!request) return
    if (event.conditionDraft) request.draft = event.conditionDraft
    if (event.kind === 'generation_started') {
      request.started = true
      // 채팅은 이 순간 대화 화면에서 생성 화면으로 바뀐다. 조건 카드가 생성 화면으로 이어지게 한다.
      if (visible.current) show('generating', request)
      else withViewTransition(() => show('generating', request))
    } else if (event.kind === 'generation_finished' && event.status === 'completed')
      // 실패한 생성은 저장할 것이 없다. 「초안 작성」에서 멈춘 것으로 보이게 다음 줄로 넘기지 않는다.
      show('verifying', request)
    // Keep the original key/body and the last validated conditions on tab reload.
    try {
      writeRequest(request)
    } catch {
      /* The existing journal still guards the original POST. */
    }
  }
  const load = async (request = active.current ?? own): Promise<boolean> => {
    if (!request?.result || reading.current) return false
    reading.current = true
    show('loading', request)
    try {
      const [steps, screen, messages] = await Promise.all([
        planningApi.stepsSnapshot(request.eventId),
        planningApi.get(request.eventId),
        planningApi.messages(request.eventId),
      ])
      const status = generatedSnapshotStatus(request, request.result, steps)
      if (
        status !== 'new' ||
        screen.baseRevision !== steps.baseRevision ||
        screen.planRevision !== steps.planRevision
      ) {
        show(
          status === 'changed' || screen.baseRevision > request.result.baseRevision
            ? 'changed'
            : 'unconfirmed',
          request,
        )
        return false
      }
      queryClient.setQueryData(planningSnapshotKey(userId, clubId, request.eventId), {
        screen,
        messages,
        steps: steps.steps,
      })
      if (!mounted.current) return false
      // Publish only the verified snapshot. Route replacement cannot reveal cached old steps.
      removeRequest(request)
      active.current = null
      setFlow(null)
      onGenerated(request.eventId, steps.steps.length, request.key)
      return true
    } catch {
      show('load-failed', request)
      return false
    } finally {
      reading.current = false
    }
  }
  const finish = async (result: S['PlanViewOut']) => {
    const request = active.current
    if (!request) return false
    request.result = result
    request.draft = result.draft
    if (result.generationResult?.status === 'generated') {
      try {
        writeRequest(request)
      } catch {
        /* Keep the in-memory result; the earlier journal remains locked. */
      }
      return load(request)
    }
    removeRequest(request)
    active.current = null
    if (mounted.current) setFlow(null)
    return false
  }
  const fail = (cause: unknown) => {
    const request = active.current
    // Known request/state rejection is final. A generic API/transport error may follow a commit.
    const rejected =
      cause instanceof ApiError &&
      [
        'VERSION_CONFLICT',
        'EVENT_NOT_PLANNING',
        'FORBIDDEN',
        'UNAUTHORIZED',
        'EVENT_NOT_FOUND',
        'VALIDATION_FAILED',
        'PLANNING_STATE_CONFLICT',
        'PLAN_EDITED_CONFLICT',
        'AI_UNAVAILABLE',
      ].includes(cause.code)
    if (request && !rejected) show('unknown', request)
    else {
      if (request) removeRequest(request)
      active.current = null
      if (mounted.current) setFlow(null)
    }
    return !!request && !rejected
  }
  const viewCurrent = async () => {
    const request = active.current ?? own
    if (!request?.result || reading.current) return
    reading.current = true
    show('loading', request)
    try {
      const [screen, messages, steps] = await Promise.all([
        planningApi.get(request.eventId),
        planningApi.messages(request.eventId),
        planningApi.stepsSnapshot(request.eventId),
      ])
      if (
        !steps.steps.length ||
        screen.baseRevision !== steps.baseRevision ||
        screen.planRevision !== steps.planRevision
      ) {
        show('changed', request)
        return
      }
      if (!mounted.current) return
      queryClient.setQueryData(planningSnapshotKey(userId, clubId, request.eventId), {
        screen,
        messages,
        steps: steps.steps,
      })
      removeRequest(request)
      active.current = null
      setFlow(null)
      onGenerated(request.eventId, 0, request.key)
    } catch {
      show('changed', request)
    } finally {
      reading.current = false
    }
  }
  // 결과를 모르는 요청(연결 끊김, 새로고침 뒤 남은 탭 기록)을 요청 키로 조회해 푼다(#342).
  //   채팅 abc 전송 → 배포로 끊김 → GET /plan/requests/abc
  //     completed → 받았어야 할 응답으로 이어 간다. 초안이면 load()로 확인한 뒤 P2
  //     processing → 3초 뒤 다시 조회. 그동안 이 행사만 잠긴다
  //     not_saved → 탭 기록을 지워 잠금을 풀고, 다시 보내 달라고 안내한다
  // POST를 다시 보내지 않는다. 지워진 키나 오래된 처리 기록이 모델을 한 번 더 실행할 수 있다.
  const settle = async (request: PlanningRequest, result: S['PlanViewOut']) => {
    request.result = result
    request.draft = result.draft
    if (result.generationResult?.status === 'generated') {
      active.current = request
      try {
        writeRequest(request)
      } catch {
        /* load() still verifies the saved snapshot from memory. */
      }
      await load(request)
      return
    }
    release(request, { result, saved: true })
  }
  const release = (request: PlanningRequest, settled: RequestSettled) => {
    removeRequest(request)
    if (active.current?.key === request.key) active.current = null
    if (mounted.current) setFlow(null)
    void queryClient.invalidateQueries({
      queryKey: planningSnapshotKey(userId, clubId, request.eventId),
    })
    onSettled(settled)
  }
  const shown = flow ?? restoredFlow
  visible.current = !!shown
  const unresolved = shown?.phase === 'unknown' ? (active.current ?? own) : null
  // 초안 생성이 시작되지 않은 채팅은 초안 생성 화면을 띄우지 않고 대화 화면에서 확인한다(#368).
  // 조회와 잠금(blocked)은 그대로 두고, 화면에 넘기는 flow만 비운다.
  const checking = checksInChat(unresolved, shown?.phase)
  const unresolvedKey = unresolved?.key
  const settleRef = useRef({ settle, release })
  settleRef.current = { settle, release }
  useEffect(() => {
    if (!unresolved) return
    const request = unresolved
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const check = async () => {
      try {
        const lookup = await planningApi.request(request.eventId, request.key)
        if (stopped) return
        const step = recoveryStep(lookup)
        if (step === 'apply' && lookup.result)
          await settleRef.current.settle(request, lookup.result)
        else if (step === 'release') {
          const saved = lookup.status === 'completed'
          const text =
            !saved && request.kind === 'chat'
              ? (request.body as S['PlanChatIn']).message
              : undefined
          settleRef.current.release(request, { saved, text })
        } else timer = setTimeout(check, LOOKUP_RETRY_MS)
      } catch {
        // 배포 중이면 서버가 잠시 응답하지 않는다. 같은 요청을 다시 묻기만 한다.
        if (!stopped) timer = setTimeout(check, LOOKUP_RETRY_MS)
      }
    }
    void check()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
    // 같은 요청 키에는 조회 루프를 하나만 둔다. 화면이 다시 그려져도 새로 시작하지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unresolvedKey])
  return {
    isCurrent: () => mounted.current,
    begin,
    progress,
    finish,
    fail,
    load: () => load(),
    viewCurrent,
    flow: checking ? null : shown,
    // 대화 화면에서 결과를 확인하는 중인 채팅이 있는가(#368).
    checking,
    blocked: !!journal.raw,
    journal,
  }
}
