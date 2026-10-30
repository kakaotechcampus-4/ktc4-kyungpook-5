import { apiGet, apiPost } from '@/shared/api/client'
import { loadLocalPlan, saveLocalPlan } from '@/features/planning/localPlan'
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

  // --- 아래 둘은 서버 경로가 아직 없다(#213) ----------------------------------
  // 화면 흐름을 먼저 잇기 위해 이 브라우저에만 적어둔다. 엔드포인트가 생기면
  // 본문만 apiPost 한 줄로 바꾸면 되고, 부르는 쪽은 손대지 않아도 된다.
  //   saveSteps → PATCH /events/{eventId}/plan/steps
  //   start     → POST  /events/{eventId}/start
  saveSteps: (eventId: string, codes: string[]) =>
    Promise.resolve(saveLocalPlan(eventId, { codes })),
  start: (eventId: string) => Promise.resolve(saveLocalPlan(eventId, { started: true })),
  local: (eventId: string) => loadLocalPlan(eventId),
}
