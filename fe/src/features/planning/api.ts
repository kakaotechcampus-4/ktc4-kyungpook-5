import { apiGet, apiPatch, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { streamPlan, type PlanStreamHandlers } from './stream'

type S = components['schemas']
const plan = (eventId: string) => `/events/${encodeURIComponent(eventId)}/plan`
export const planningApi = {
  create: (clubId: string) => apiPost<S['EventCreateOut']>('/events', { clubId }),
  drafts: (clubId: string) =>
    apiGet<S['DraftOut'][]>(`/events/drafts?clubId=${encodeURIComponent(clubId)}`),
  get: (eventId: string) => apiGet<S['PlanScreenOut']>(plan(eventId)),
  messages: (eventId: string) => apiGet<S['PlanMessageOut'][]>(`${plan(eventId)}/messages`),
  steps: (eventId: string) => apiGet<S['PlannedStepOut'][]>(`${plan(eventId)}/steps`),
  // 응답 도중 끊긴 요청의 결과만 읽는다. 모델을 다시 부르지 않는다(#342).
  request: (eventId: string, key: string) =>
    apiGet<S['PlanRequestOut']>(`${plan(eventId)}/requests/${encodeURIComponent(key)}`),
  stepsSnapshot: (eventId: string) =>
    apiGet<S['PlanStepsSnapshotOut']>(`${plan(eventId)}/steps/snapshot`),
  chat: (eventId: string, body: S['PlanChatIn']) =>
    apiPost<S['PlanViewOut']>(`${plan(eventId)}/chat`, body),
  generate: (eventId: string, body: S['PlanGenerateIn']) =>
    apiPost<S['PlanViewOut']>(`${plan(eventId)}/generate`, body),
  // 진행 단계와 답변 조각을 차례로 받는 SSE 경로(#285). 본문은 위와 같다.
  chatStream: (eventId: string, body: S['PlanChatIn'], key: string, handlers: PlanStreamHandlers) =>
    streamPlan(`${plan(eventId)}/chat/stream`, body, key, handlers),
  generateStream: (
    eventId: string,
    body: S['PlanGenerateIn'],
    key: string,
    handlers: PlanStreamHandlers,
  ) => streamPlan(`${plan(eventId)}/generate/stream`, body, key, handlers),

  review: (eventId: string, expectedRevision: number) =>
    apiPost<S['PlanReviewOut']>(`${plan(eventId)}/review`, { expectedRevision }),

  // 단계·Action 세부 수정 (#106 ④)
  updateStep: (stepId: string, body: S['StepUpdateIn']) =>
    apiPatch<S['PlannedStepOut']>(`/steps/${encodeURIComponent(stepId)}`, body),
  updateAction: (actionId: string, body: S['ActionUpdateIn']) =>
    apiPatch<S['PlannedStepOut']>(`/actions/${encodeURIComponent(actionId)}`, body),

  saveSteps: (eventId: string, codes: string[], expectedRevision: number) =>
    apiPatch<S['PlannedStepOut'][]>(`${plan(eventId)}/steps`, {
      codes,
      expectedRevision,
    }),
  start: (eventId: string) => apiPost<S['EventStartOut']>(`${plan(eventId).replace(/\/plan$/, '')}/start`, {}),
}
