import { apiGet, apiPost, apiPostForm } from '@/shared/api/client'
import type { ClubRecord, RecordDetail, UploadRecordInput } from '@/features/records/types'

export function uploadRecord({ clubId, category, file }: UploadRecordInput) {
  const form = new FormData()
  form.append('clubId', clubId)
  form.append('category', category)
  form.append('file', file)
  return apiPostForm<ClubRecord>('/records', form)
}

export function getRecord(recordId: string) {
  return apiGet<RecordDetail>(`/records/${encodeURIComponent(recordId)}`)
}

export function getRecords(clubId: string) {
  return apiGet<ClubRecord[]>(`/records?clubId=${encodeURIComponent(clubId)}`)
}

export function retryRecordIndex(recordId: string) {
  return apiPost<RecordDetail>(`/records/${encodeURIComponent(recordId)}/index`)
}
