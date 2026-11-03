import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExpense, getExpenses } from './api'
import type { CreateExpenseInput } from './types'
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
