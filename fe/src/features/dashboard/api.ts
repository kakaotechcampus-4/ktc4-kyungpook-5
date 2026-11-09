import { apiGet, apiPost, apiDownload } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
export const dashboardApi = {
  briefing: (clubId: string) =>
    apiGet<S['ToriBriefingOut']>(`/clubs/${encodeURIComponent(clubId)}/tori/briefing`),
  message: (clubId: string, input: S['ToriMessageIn']) =>
    apiPost<S['ToriMessageOut']>(`/clubs/${encodeURIComponent(clubId)}/tori/messages`, input),
  download: (id: string, name: string) =>
    apiDownload(`/records/${encodeURIComponent(id)}/file`, name),
}
