import { apiDelete, apiGetPage, apiPatch, apiPost } from '@/shared/api/client'
import type {
  CreateExpenseInput,
  Expense,
  ExpensePageMeta,
  UpdateExpenseInput,
} from './types'

export const EXPENSE_PAGE_SIZE = 20

export function getExpenses(clubId: string, page: number) {
  return apiGetPage<Expense, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/expenses?page=${page}&size=${EXPENSE_PAGE_SIZE}`,
  )
}

export function createExpense(clubId: string, body: CreateExpenseInput) {
  return apiPost<Expense>(`/clubs/${encodeURIComponent(clubId)}/expenses`, body)
}

// 보낸 밭만 바뀐다. expectedVersion 은 조회에서 받은 값을 그대로 돌려보낸다 —
// 그사이 바뀌었으면 서버가 409 로 거절한다.
export function updateExpense(clubId: string, expenseId: string, body: UpdateExpenseInput) {
  return apiPatch<Expense>(
    `/clubs/${encodeURIComponent(clubId)}/expenses/${encodeURIComponent(expenseId)}`,
    body,
  )
}

export function deleteExpense(clubId: string, expenseId: string) {
  return apiDelete<void>(
    `/clubs/${encodeURIComponent(clubId)}/expenses/${encodeURIComponent(expenseId)}`,
  )
}
