import { apiDelete, apiGet, apiGetPage, apiPatch, apiPost, apiPostForm } from '@/shared/api/client'
import type { CreateExpenseInput, Expense, ExpensePageMeta, ReceiptImport, ReceiptImportListItem, ReceiptDraft, ReceiptConfirm, UpdateExpenseInput } from './types'

export const EXPENSE_PAGE_SIZE = 20

export function getExpenses(clubId: string, page: number) {
  return apiGetPage<Expense, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/expenses?page=${page}&size=${EXPENSE_PAGE_SIZE}`,
  )
}

export function createExpense(clubId: string, body: CreateExpenseInput) {
  return apiPost<Expense>(`/clubs/${encodeURIComponent(clubId)}/expenses`, body)
}

// 회장·임원만 고칠 수 있다. 그사이 누가 먼저 고쳤으면 409 VERSION_CONFLICT 다.
export function updateExpense(clubId: string, expenseId: string, body: UpdateExpenseInput) {
  return apiPatch<Expense>(
    `/clubs/${encodeURIComponent(clubId)}/expenses/${encodeURIComponent(expenseId)}`,
    body,
  )
}

// 되돌릴 수 없다. 204라 돌려줄 본문이 없다.
export function deleteExpense(clubId: string, expenseId: string) {
  return apiDelete<void>(
    `/clubs/${encodeURIComponent(clubId)}/expenses/${encodeURIComponent(expenseId)}`,
  )
}

export function getReceiptImports(clubId: string) {
  return apiGetPage<ReceiptImportListItem, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/receipt-imports?page=1&size=20`,
  )
}

export function retryReceiptImport(clubId: string, importId: string) {
  return apiPost<ReceiptImport>(
    `/clubs/${encodeURIComponent(clubId)}/receipt-imports/${encodeURIComponent(importId)}/retry`,
  )
}

export function uploadReceipt(clubId: string, file: File) {
  const form = new FormData()
  form.append('type', 'RECEIPT_IMAGE')
  form.append('file', file)
  return apiPostForm<ReceiptImport>(`/clubs/${encodeURIComponent(clubId)}/receipt-imports`, form)
}
export function getReceiptImport(clubId: string, id: string) {
  return apiGet<ReceiptImport>(`/clubs/${encodeURIComponent(clubId)}/receipt-imports/${encodeURIComponent(id)}`)
}
export function saveReceiptDraft(clubId: string, id: string, body: ReceiptDraft) {
  return apiPatch<ReceiptImport>(`/clubs/${encodeURIComponent(clubId)}/receipt-imports/${encodeURIComponent(id)}/draft`, body)
}
// eventId: 확정으로 만드는 지출 전부를 이 행사에 연결한다(#367). null이면 연결하지 않는다.
export function confirmReceiptImport(clubId: string, id: string, version: number, eventId: string | null) {
  return apiPost<ReceiptConfirm>(`/clubs/${encodeURIComponent(clubId)}/receipt-imports/${encodeURIComponent(id)}/confirm`, { expectedVersion: version, eventId })
}
