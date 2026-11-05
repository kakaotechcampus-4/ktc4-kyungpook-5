import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { planningApi } from './api'
import {
  generatedSnapshotStatus,
  parseRequest,
  readRequestText,
  removeRequest,
  subscribeRequest,
  writeRequest,
  type GenerationFlow,
  type PlanningRequest,
} from './generation'
import type { PlanProgress } from './types'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'

type S = components['schemas']
export const planningSnapshotKey = (
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
) => ['planning', 'snapshot', userId, clubId, eventId]

export function usePlanningRequestJournal(userId: string | undefined, clubId: string | null) {
  const raw = useSyncExternalStore(
    subscribeRequest,
    () => readRequestText(userId, clubId),
    () => null,
  )
  return { raw, request: parseRequest(raw, userId, clubId) }
}

// The chat hook owns the stream. This hook only tracks the request and reads its saved result.
export function useGenerationRequest(
  userId: string | undefined,
  clubId: string | null,
  eventId: string | null,
  onGenerated: (eventId: string, count: number, key: string) => void,
) {
  const queryClient = useQueryClient()
  const journal = usePlanningRequestJournal(userId, clubId)
  const active = useRef<PlanningRequest | null>(null)
  const mounted = useRef(true)
  const [flow, setFlow] = useState<GenerationFlow | null>(null)
  const reading = useRef(false)
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
  const own = journal.request?.eventId === eventId ? journal.request : null
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
    if (!userId || !clubId || readRequestText(userId, clubId)) throw new Error('REQUEST_LOCKED')
    if (kind === 'button' && mounted.current) setFlow({ phase: 'requesting', draft })
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
      show('generating', request)
    } else if (event.kind === 'generation_finished') show('verifying', request)
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
  return {
    isCurrent: () => mounted.current,
    begin,
    progress,
    finish,
    fail,
    load: () => load(),
    viewCurrent,
    flow: flow ?? restoredFlow,
    blocked: !!journal.raw,
    journal,
  }
}
