import {
  apiDownload,
  apiGet,
  apiGetEnvelope,
  apiGetPage,
  apiPost,
  apiPostForm,
} from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
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

export const RECORD_PAGE_SIZE = 20

export function getRecords(clubId: string, page: number) {
  return apiGetPage<ClubRecord, components['schemas']['PageMeta']>(
    `/records?clubId=${encodeURIComponent(clubId)}&page=${page}&size=${RECORD_PAGE_SIZE}`,
  )
}

export function retryRecordIndex(recordId: string) {
  return apiPost<RecordDetail>(`/records/${encodeURIComponent(recordId)}/index`)
}

export function downloadRecord(recordId: string, fileName: string) {
  return apiDownload(`/records/${encodeURIComponent(recordId)}/file`, fileName)
}

export function searchRecords(clubId: string, query: string, page: number) {
  const params = new URLSearchParams({ clubId, query, page: String(page), size: '20' })
  return apiGetEnvelope<
    components['schemas']['RecordSearchData'],
    components['schemas']['PageMeta']
  >(`/records/search?${params}`)
}
