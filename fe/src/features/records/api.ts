import {
  apiDelete,
  apiDownload,
  apiGet,
  apiGetEnvelope,
  apiGetPage,
  apiPost,
  apiPostForm,
} from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import type {
  ClubRecord,
  RecordCategory,
  RecordDetail,
  UploadRecordInput,
} from '@/features/records/types'

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

// category를 빼면 모든 분류를 받는다. totalCount도 고른 분류 기준으로 온다.
export function getRecords(clubId: string, page: number, category?: RecordCategory) {
  const params = new URLSearchParams({ clubId, page: String(page), size: String(RECORD_PAGE_SIZE) })
  if (category) params.set('category', category)
  return apiGetPage<ClubRecord, components['schemas']['PageMeta']>(`/records?${params}`)
}

// 칩 건수. 분류마다 1페이지를 받던 것을 이 한 번으로 대신한다(#287).
// 자료가 없는 분류도 0으로 채워 오므로 화면에서 빈 칸을 메울 필요가 없다.
export function getRecordCategoryCounts(clubId: string) {
  return apiGet<components['schemas']['RecordCategoryCountsOut']>(
    `/records/category-counts?clubId=${encodeURIComponent(clubId)}`,
  )
}

// 되돌릴 수 없다. 원본 파일과 검색 색인이 함께 사라진다. 204라 돌려줄 본문이 없다.
export function deleteRecord(recordId: string) {
  return apiDelete<void>(`/records/${encodeURIComponent(recordId)}`)
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
