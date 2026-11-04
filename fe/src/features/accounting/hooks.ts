import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExpense, getExpenses, getReceiptImports, retryReceiptImport, getReceiptImport, uploadReceipt, saveReceiptDraft, confirmReceiptImport } from './api'
import type { CreateExpenseInput, ReceiptDraft } from './types'
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

export function expenseFormErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const reason = error.fields && Object.values(error.fields)[0]
    if (reason) return reason
    if (error.code === 'FORBIDDEN') return '지출을 등록할 권한이 없어요. 회장·임원만 등록할 수 있어요.'
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
  }
  return '지출을 등록하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
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
    onSettled: () => client.invalidateQueries({ queryKey: ['accounting', clubId, 'receipt-imports'] }),
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
    confirm: useMutation({ mutationFn: ({id, version}: {id: string; version: number}) => confirmReceiptImport(clubId, id, version), onSettled: refresh }),
  }
}
