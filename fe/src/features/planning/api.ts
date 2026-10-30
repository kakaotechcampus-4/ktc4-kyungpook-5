import { apiGet, apiPatch, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
const plan = (eventId: string) => `/events/${encodeURIComponent(eventId)}/plan`
export const planningApi = {
  create: (clubId: string) => apiPost<S['EventCreateOut']>('/events', { clubId }),
  drafts: (clubId: string) =>
    apiGet<S['DraftOut'][]>(`/events/drafts?clubId=${encodeURIComponent(clubId)}`),
  get: (eventId: string) => apiGet<S['PlanScreenOut']>(plan(eventId)),
  messages: (eventId: string) => apiGet<S['PlanMessageOut'][]>(`${plan(eventId)}/messages`),
  steps: (eventId: string) => apiGet<S['PlannedStepOut'][]>(`${plan(eventId)}/steps`),
  chat: (eventId: string, body: S['PlanChatIn']) =>
    apiPost<S['PlanViewOut']>(`${plan(eventId)}/chat`, body),
  generate: (eventId: string, body: S['PlanGenerateIn']) =>
    apiPost<S['PlanViewOut']>(`${plan(eventId)}/generate`, body),

  // 단계·Action 세부 수정 (#106 ④)
  updateStep: (stepId: string, body: S['StepUpdateIn']) =>
    apiPatch<S['PlannedStepOut']>(`/steps/${encodeURIComponent(stepId)}`, body),
  updateAction: (actionId: string, body: S['ActionUpdateIn']) =>
    apiPatch<S['PlannedStepOut']>(`/actions/${encodeURIComponent(actionId)}`, body),

  // 단계 구성·상태 전이 (#213 3단계)
  saveSteps: (eventId: string, codes: string[]) =>
    apiPatch<S['PlannedStepOut'][]>(`/events/${encodeURIComponent(eventId)}/plan/steps`, {
      codes,
    }),
  start: (eventId: string) =>
    apiPost<S['EventStartOut']>(`/events/${encodeURIComponent(eventId)}/start`),
  complete: (eventId: string) =>
    apiPost<S['EventStatusOut']>(`/events/${encodeURIComponent(eventId)}/complete`),
}
