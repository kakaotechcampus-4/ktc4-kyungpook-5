import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getRecord,
  getRecords,
  retryRecordIndex,
  searchRecords,
  uploadRecord,
} from '@/features/records/api'
import { RECORD_CATEGORIES } from '@/features/records/presentation'
import type {
  RecordCategory,
  RecordFilter,
  RecordParseStatus,
  UploadRecordInput,
} from '@/features/records/types'
import { ApiError } from '@/shared/api/types'

const listKey = (clubId: string) => ['records', clubId, 'list'] as const

// 분류는 listKey 뒤에 붙여, 업로드 뒤 listKey 무효화가 모든 분류 목록에 닿게 한다.
// 칩 건수 때문에 분류마다 같이 받으므로, 30초 안의 칩 전환·재진입·창 포커스로는 다시 받지 않는다.
// 30초가 지나면 창 포커스로 다시 받아, 다른 탭이나 팀원이 올린 자료도 돌아왔을 때 보인다.
const listQuery = (clubId: string, page: number, category?: RecordCategory) => ({
  queryKey: [...listKey(clubId), category ?? 'ALL', page] as const,
  queryFn: () => getRecords(clubId, page, category),
  enabled: Boolean(clubId),
  retry: false,
  staleTime: 30_000,
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

const COUNT_FILTERS: RecordFilter[] = ['ALL', ...RECORD_CATEGORIES.map((item) => item.value)]

// 칩 건수. 분류마다 1페이지를 받아 totalCount를 읽는다. 목록과 같은 키라 칩을 바꾸면 캐시로 바로 뜬다.
// meta가 없으면 받은 행 수로 대신한다(패널의 페이지 계산과 같은 기준).
// ponytail: 분류 수만큼 요청한다(지금 6번). 분류가 늘면 BE에 분류별 건수 API를 요청한다.
export function useRecordCounts(clubId: string) {
  return useQueries({
    queries: COUNT_FILTERS.map((filter) =>
      listQuery(clubId, 1, filter === 'ALL' ? undefined : filter),
    ),
    combine: (results) =>
      Object.fromEntries(
        COUNT_FILTERS.map((filter, index) => {
          const page = results[index].data
          return [filter, page ? (page.meta?.totalCount ?? page.data.length) : undefined]
        }),
      ) as Record<RecordFilter, number | undefined>,
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

// 목록 응답에 상태가 이미 있다. 끝난 자료(INDEXED·NEEDS_REVIEW)는 상세를 받지 않아 칩을 바꿀 때 행마다
// 요청이 나가지 않게 한다. 처리 중이면 상태를 따라가고, FAILED면 실패 사유(parseError)를 받는다.
// 「상태 다시 확인」의 refetch는 enabled와 상관없이 동작한다.
export function useRecordDetail(clubId: string, recordId: string, listStatus: RecordParseStatus) {
  return useQuery({
    queryKey: ['records', clubId, recordId],
    queryFn: () => getRecord(recordId),
    enabled:
      Boolean(clubId && recordId) && listStatus !== 'INDEXED' && listStatus !== 'NEEDS_REVIEW',
    retry: false,
    // COMPLETED는 파싱 완료다. 서버가 색인을 시작하면 INDEXED까지 이어서 확인한다.
    refetchInterval: (query) => {
      // 서버가 거절한 오류(권한·없는 자료 등)는 멈춘다. 잠깐 끊긴 네트워크 오류는 계속 따라간다.
      if (query.state.error instanceof ApiError) return false
      if (query.state.data?.indexError) return false
      const status = query.state.data?.parseStatus ?? listStatus
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
