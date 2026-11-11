import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteRecord,
  getRecord,
  getRecordCategoryCounts,
  getRecords,
  retryRecordIndex,
  searchRecords,
  uploadRecord,
} from '@/features/records/api'
import { isExpenseEvidence, RECORD_CATEGORIES } from '@/features/records/presentation'
import type {
  ClubRecord,
  RecordCategory,
  RecordFilter,
  UploadRecordInput,
} from '@/features/records/types'
import { ApiError } from '@/shared/api/types'

const listKey = (clubId: string) => ['records', clubId, 'list'] as const
const countsKey = (clubId: string) => ['records', clubId, 'category-counts'] as const

// 분류는 listKey 뒤에 붙여, 업로드 뒤 listKey 무효화가 모든 분류 목록에 닿게 한다.
// 30초 안의 칩 전환·재진입·창 포커스로는 다시 받지 않는다. 30초가 지나면 창 포커스로
// 다시 받아, 다른 탭이나 팀원이 올린 자료도 돌아왔을 때 보인다.
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
      // 목록과 칩 건수가 함께 달라진다. 키 앞부분을 지워 둘 다 닿게 한다.
      void queryClient.invalidateQueries({ queryKey: ['records', clubId] })
    },
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['records', clubId] })
  return { records, upload, refresh }
}

// 칩 건수. 분류마다 1페이지를 받아 totalCount를 읽던 것을 한 번의 호출로 바꿨다(#287, #288).
// 자료가 없는 분류도 0으로 채워 오므로 화면이 빈 칸을 메울 필요가 없다.
//
// 생성 타입의 byCategory는 {[key: string]: number}라 분류 키로 좁혀 쓴다.
export function useRecordCounts(clubId: string) {
  const counts = useQuery({
    queryKey: countsKey(clubId),
    queryFn: () => getRecordCategoryCounts(clubId),
    enabled: Boolean(clubId),
    retry: false,
    staleTime: 30_000,
  })
  // 아직 못 받았으면 전부 undefined다 — 화면이 칩에서 건수를 숨긴다.
  const data = counts.data
  return {
    ALL: data?.all,
    ...(Object.fromEntries(
      RECORD_CATEGORIES.map(({ value }) => [value, data?.byCategory[value]]),
    ) as Record<RecordCategory, number | undefined>),
  } as Record<RecordFilter, number | undefined>
}

// 목록·칩 건수·그 자료의 상세가 한꺼번에 달라진다. 업로드와 같은 범위를 지운다.
export function useDeleteRecord(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (recordId: string) => deleteRecord(recordId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['records', clubId] })
    },
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
// 지출 증빙(영수증 사진)은 색인하지 않아 상태가 바뀌지 않으므로 받지도 따라가지도 않는다.
// 「상태 다시 확인」의 refetch는 enabled와 상관없이 동작한다.
export function useRecordDetail(clubId: string, record: ClubRecord) {
  const recordId = record.id
  const listStatus = record.parseStatus
  return useQuery({
    queryKey: ['records', clubId, recordId],
    queryFn: () => getRecord(recordId),
    enabled:
      Boolean(clubId && recordId) &&
      listStatus !== 'INDEXED' &&
      listStatus !== 'NEEDS_REVIEW' &&
      !isExpenseEvidence(record),
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
