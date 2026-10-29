import { apiGetPage } from '@/shared/api/client'
import type { Expense, ExpensePageMeta } from './types'

export const EXPENSE_PAGE_SIZE = 20

export function getExpenses(clubId: string, page: number) {
  return apiGetPage<Expense, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/expenses?page=${page}&size=${EXPENSE_PAGE_SIZE}`,
  )
}
