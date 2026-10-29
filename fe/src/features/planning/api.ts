import { apiGet, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
export const planningApi = {
  create: (clubId: string) => apiPost<S['EventCreateOut']>('/events', { clubId }),
  get: (eventId: string) =>
    apiGet<S['PlanScreenOut']>(`/events/${encodeURIComponent(eventId)}/plan`),
  chat: (eventId: string, body: S['PlanChatIn']) =>
    apiPost<S['PlanViewOut']>(`/events/${encodeURIComponent(eventId)}/plan/chat`, body),
}
