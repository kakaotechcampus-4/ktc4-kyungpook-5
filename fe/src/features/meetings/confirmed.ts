import { apiGet, apiPatch, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
type Schemas = components['schemas']
export type Recipient = Schemas['ReminderRecipientOut']
export type ConfirmedTask = Schemas['ConfirmedTaskOut']
export type ConfirmedFields = Omit<Schemas['TaskSuggestionConfirmIn'], 'expectedVersion'>
const path = (club: string) => `/clubs/${encodeURIComponent(club)}`
export const confirmedApi = {
  recipients: (club: string) => apiGet<Recipient[]>(`${path(club)}/reminder-recipients`),
  list: (club: string) => apiGet<ConfirmedTask[]>(`${path(club)}/confirmed-tasks`),
  get: (club: string, id: string) =>
    apiGet<ConfirmedTask>(`${path(club)}/confirmed-tasks/${encodeURIComponent(id)}`),
  confirm: (club: string, id: string, version: number, fields: ConfirmedFields) =>
    apiPost<ConfirmedTask>(`${path(club)}/task-suggestions/${encodeURIComponent(id)}/confirm`, {
      expectedVersion: version,
      ...fields,
    }),
  update: (club: string, item: ConfirmedTask, fields: ConfirmedFields) =>
    apiPatch<ConfirmedTask>(`${path(club)}/confirmed-tasks/${encodeURIComponent(item.id)}`, {
      expectedVersion: item.version,
      ...fields,
    }),
  cancel: (club: string, item: ConfirmedTask) =>
    apiPost<ConfirmedTask>(`${path(club)}/confirmed-tasks/${encodeURIComponent(item.id)}/cancel`, {
      expectedVersion: item.version,
    }),
}
export function seoulInput(iso: string | null) {
  return iso ? new Date(new Date(iso).getTime() + 9 * 3600000).toISOString().slice(0, 16) : ''
}
export function seoulIso(value: string) {
  return new Date(`${value}:00+09:00`).toISOString()
}
export function displayTime(iso: string | null) {
  return iso
    ? new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul',
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(iso))
    : '미정'
}
