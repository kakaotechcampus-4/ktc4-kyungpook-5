import { apiGet, apiGetPage, apiPatch, apiPost, apiPostForm } from '@/shared/api/client'
import type { CreateExpenseInput, Expense, ExpensePageMeta, ReceiptImport, ReceiptImportListItem, ReceiptDraft, ReceiptConfirm } from './types'

export const EXPENSE_PAGE_SIZE = 20

export function getExpenses(clubId: string, page: number) {
  return apiGetPage<Expense, ExpensePageMeta>(
    `/clubs/${encodeURIComponent(clubId)}/expenses?page=${page}&size=${EXPENSE_PAGE_SIZE}`,
  )
}

export function createExpense(clubId: string, body: CreateExpenseInput) {
  return apiPost<Expense>(`/clubs/${encodeURIComponent(clubId)}/expenses`, body)
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
export function confirmReceiptImport(clubId: string, id: string, version: number) {
  return apiPost<ReceiptConfirm>(`/clubs/${encodeURIComponent(clubId)}/receipt-imports/${encodeURIComponent(id)}/confirm`, { expectedVersion: version })
}
