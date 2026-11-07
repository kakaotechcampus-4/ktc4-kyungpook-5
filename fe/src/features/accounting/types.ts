import type { components } from '@/shared/api/schema'

export type Expense = components['schemas']['ExpenseOut']
export type ExpensePageMeta = components['schemas']['PageMeta']
export type CreateExpenseInput = components['schemas']['ExpenseCreateIn']
// expectedVersion 이 필수다. 보낸 밭만 바뀌고 null 을 보내면 그 값을 비운다.
export type UpdateExpenseInput = components['schemas']['ExpenseUpdateIn']

export type ReceiptImport = components['schemas']['ReceiptImportOut']
export type ReceiptImportListItem = components['schemas']['ReceiptImportListItemOut']
export type ReceiptDraft = components['schemas']['ReceiptImportDraftIn']
export type ReceiptConfirm = components['schemas']['ReceiptImportConfirmOut']
