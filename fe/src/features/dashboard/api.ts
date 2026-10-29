import { apiGet, apiGetPage, apiPost, apiDownload } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
export const dashboardApi = {
  message: (clubId: string, message: string) =>
    apiPost<S['ToriMessageOut']>(`/clubs/${encodeURIComponent(clubId)}/tori/messages`, { message }),
  download: (id: string, name: string) =>
    apiDownload(`/records/${encodeURIComponent(id)}/file`, name),
  tasks: (clubId: string) =>
    apiGet<S['ConfirmedTaskOut'][]>(`/clubs/${encodeURIComponent(clubId)}/confirmed-tasks`),
  events: (clubId: string) =>
    apiGetPage<S['EventOut'], S['PageMeta']>(
      `/events?${new URLSearchParams({ clubId, status: 'ON_GOING', page: '1', size: '5' })}`,
    ),
}
