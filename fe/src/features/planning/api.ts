import { apiGet, apiPost } from '@/shared/api/client'
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
}
