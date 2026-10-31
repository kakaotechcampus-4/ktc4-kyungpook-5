import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExpense, deleteExpense, getExpenses, updateExpense } from './api'
import type { CreateExpenseInput, Expense, UpdateExpenseInput } from './types'
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
    mutationFn: ({ expense, body }: { expense: Expense; body: UpdateExpenseInput }) =>
      updateExpense(clubId, expense.id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting', clubId, 'expenses'] }),
  })
}

export function useDeleteExpense(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (expense: Expense) => deleteExpense(clubId, expense.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounting', clubId, 'expenses'] }),
  })
}

export function expenseFormErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const reason = error.fields && Object.values(error.fields)[0]
    if (reason) return reason
    if (error.code === 'VERSION_CONFLICT')
      return '내용이 그사이 바뀌었어요. 새로고침한 뒤 다시 고쳐 주세요.'
    if (error.code === 'FORBIDDEN') return '회장·임원만 지출을 고치거나 지울 수 있어요.'
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
  }
  return '지출을 등록하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
}
