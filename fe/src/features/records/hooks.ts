import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getRecord,
  getRecords,
  retryRecordIndex,
  searchRecords,
  uploadRecord,
} from '@/features/records/api'
import type { RecordCategory, UploadRecordInput } from '@/features/records/types'

const listKey = (clubId: string) => ['records', clubId, 'list'] as const

// 분류는 listKey 뒤에 붙여, 업로드 뒤 listKey 무효화가 모든 분류 목록에 닿게 한다.
const listQuery = (clubId: string, page: number, category?: RecordCategory) => ({
  queryKey: [...listKey(clubId), category ?? 'ALL', page] as const,
  queryFn: () => getRecords(clubId, page, category),
  enabled: Boolean(clubId),
  retry: false,
})

// 실제 API의 업로드/목록 결과만 표시한다. 실패를 예시 결과로 바꾸지 않는다.
export function useRecordUploads(clubId: string, page: number, category?: RecordCategory) {
  const queryClient = useQueryClient()
  const records = useQuery(listQuery(clubId, page, category))
  const upload = useMutation({
    mutationFn: (input: Omit<UploadRecordInput, 'clubId'>) => uploadRecord({ ...input, clubId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listKey(clubId) })
    },
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['records', clubId] })
  return { records, upload, refresh }
}

// 칩 건수. 분류마다 1페이지를 받아 totalCount를 읽는다. 목록과 같은 키라 칩을 바꾸면 캐시로 바로 뜬다.
// ponytail: 분류 수만큼 요청한다(지금 6번). 분류가 늘면 BE에 분류별 건수 API를 요청한다.
export function useRecordCounts(clubId: string, categories: Array<RecordCategory | undefined>) {
  return useQueries({
    queries: categories.map((category) => listQuery(clubId, 1, category)),
    combine: (results) => results.map((result) => result.data?.meta?.totalCount),
  })
}

export function useRetryRecordIndex(clubId: string, recordId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => retryRecordIndex(recordId),
    onSuccess: (record) => {
      queryClient.setQueryData(['records', clubId, recordId], record)
      void queryClient.invalidateQueries({ queryKey: listKey(clubId) })
    },
  })
}

export function useRecordDetail(clubId: string, recordId: string) {
  return useQuery({
    queryKey: ['records', clubId, recordId],
    queryFn: () => getRecord(recordId),
    enabled: Boolean(clubId && recordId),
    retry: false,
    // COMPLETED는 파싱 완료다. 서버가 색인을 시작하면 INDEXED까지 이어서 확인한다.
    refetchInterval: (query) => {
      if (query.state.error) return false
      if (query.state.data?.indexError) return false
      const status = query.state.data?.parseStatus
      return status === 'QUEUED' || status === 'PARSING' || status === 'COMPLETED' ? 5000 : false
    },
  })
}

export function useRecordSearch(clubId: string, userId: string, query: string, page: number) {
  return useQuery({
    queryKey: ['records', 'search', userId, clubId, query, page],
    queryFn: () => searchRecords(clubId, query, page),
    enabled: Boolean(clubId && userId && query),
    retry: false,
    staleTime: 0,
  })
}
