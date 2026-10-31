import { apiGetPage, apiPost } from '@/shared/api/client'
import type { CreateExpenseInput, Expense, ExpensePageMeta } from './types'

export const EXPENSE_PAGE_SIZE = 20

export function getExpenses(clubId: string, page: number) {
  return apiGetPage<Expense, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/expenses?page=${page}&size=${EXPENSE_PAGE_SIZE}`,
  )
}

export function createExpense(clubId: string, body: CreateExpenseInput) {
  return apiPost<Expense>(`/clubs/${encodeURIComponent(clubId)}/expenses`, body)
}
