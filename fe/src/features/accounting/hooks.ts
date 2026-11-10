import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExpense, deleteExpense, getExpenses, getReceiptImports, retryReceiptImport, getReceiptImport, updateExpense, uploadReceipt, saveReceiptDraft, confirmReceiptImport } from './api'
import type { CreateExpenseInput, ReceiptDraft, UpdateExpenseInput } from './types'
import { ApiError } from '@/shared/api/types'

export function useExpenses(clubId: string, page: number) {
  return useQuery({
    queryKey: ['accounting', clubId, 'expenses', page],
    queryFn: () => getExpenses(clubId, page),
    enabled: Boolean(clubId),
    retry: false,
  })
}

export function useCreateExpense(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateExpenseInput) => createExpense(clubId, body),
    // 등록하면 보고 있던 목록이 곧바로 틀린 값이 된다. 페이지 전체를 다시 받는다.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting', clubId, 'expenses'] }),
  })
}

export function useUpdateExpense(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ expenseId, body }: { expenseId: string; body: UpdateExpenseInput }) =>
      updateExpense(clubId, expenseId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting', clubId, 'expenses'] }),
  })
}

// 지우면 그 페이지의 뒤 행이 한 칸씩 당겨온다. 보고 있던 페이지를 다시 받는다.
export function useDeleteExpense(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (expenseId: string) => deleteExpense(clubId, expenseId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting', clubId, 'expenses'] }),
  })
}

// 등록·수정·삭제가 같은 오류를 돌려준다. 무엇을 하려다 실패했는지만 바꿔 쓴다.
export function expenseFormErrorMessage(error: unknown, action = '등록'): string {
  if (error instanceof ApiError) {
    const reason = error.fields && Object.values(error.fields)[0]
    if (reason) return reason
    // 그사이 다른 사람이 먼저 고쳤다. 지금 보고 있는 값이 이미 옛것이라 다시 받아야 한다.
    if (error.code === 'VERSION_CONFLICT')
      return '그사이 다른 사람이 이 지출을 고쳤어요. 새로고침한 뒤 다시 시도해 주세요.'
    if (error.code === 'EXPENSE_NOT_FOUND') return '이미 지워진 지출이에요. 새로고침해 주세요.'
    if (error.code === 'FORBIDDEN') return `지출을 ${action}할 권한이 없어요. 회장·임원만 할 수 있어요.`
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
  }
  return `지출을 ${action}하지 못했어요. 잠시 뒤 다시 시도해 주세요.`
}

export function useReceiptImports(clubId: string) {
  return useQuery({
    queryKey: ['accounting', clubId, 'receipt-imports'],
    queryFn: () => getReceiptImports(clubId),
    enabled: Boolean(clubId),
    retry: false,
    refetchInterval: (query) => query.state.data?.data.some((item) => item.status === 'PROCESSING') ? 5000 : false,
  })
}

export function useRetryReceiptImport(clubId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => retryReceiptImport(clubId, id),
    // 목록과 함께 그 영수증의 상세도 다시 받는다. 실패 화면이 남아 있으면 다시 읽는 중인지 알 수 없다.
    onSettled: (_data, _error, id) => Promise.all([
      client.invalidateQueries({ queryKey: ['accounting', clubId, 'receipt-imports'] }),
      client.invalidateQueries({ queryKey: ['accounting', clubId, 'receipt-import', id] }),
    ]),
  })
}

export function useReceiptDetail(clubId: string, id: string | null) {
  return useQuery({
    queryKey: ['accounting', clubId, 'receipt-import', id],
    queryFn: () => getReceiptImport(clubId, id!),
    enabled: Boolean(id),
    retry: false,
    refetchInterval: (query) => query.state.data?.status === 'PROCESSING' ? 5000 : false,
  })
}
export function useReceiptActions(clubId: string) {
  const client = useQueryClient()
  const refresh = () => client.invalidateQueries({ queryKey: ['accounting', clubId] })
  return {
    upload: useMutation({ mutationFn: (file: File) => uploadReceipt(clubId, file), onSettled: refresh }),
    draft: useMutation({ mutationFn: ({id, body}: {id: string; body: ReceiptDraft}) => saveReceiptDraft(clubId, id, body) }),
    confirm: useMutation({ mutationFn: ({id, version, eventId}: {id: string; version: number; eventId: string | null}) => confirmReceiptImport(clubId, id, version, eventId), onSettled: refresh }),
  }
}
