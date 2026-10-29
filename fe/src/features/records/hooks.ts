import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getRecord,
  getRecords,
  retryRecordIndex,
  searchRecords,
  uploadRecord,
} from '@/features/records/api'
import type { UploadRecordInput } from '@/features/records/types'

const listKey = (clubId: string) => ['records', clubId, 'list'] as const

// 실제 API의 업로드/목록 결과만 표시한다. 실패를 예시 결과로 바꾸지 않는다.
export function useRecordUploads(clubId: string, page: number) {
  const queryClient = useQueryClient()
  const records = useQuery({
    queryKey: [...listKey(clubId), page],
    queryFn: () => getRecords(clubId, page),
    enabled: Boolean(clubId),
    retry: false,
  })
  const upload = useMutation({
    mutationFn: (input: Omit<UploadRecordInput, 'clubId'>) => uploadRecord({ ...input, clubId }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: listKey(clubId) })
    },
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['records', clubId] })
  return { records, upload, refresh }
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
