import type { components } from '@/shared/api/schema'

export type Expense = components['schemas']['ExpenseOut']
export type ExpensePageMeta = components['schemas']['PageMeta']
export type CreateExpenseInput = components['schemas']['ExpenseCreateIn']

export type ReceiptImport = components['schemas']['ReceiptImportOut']
export type ReceiptImportListItem = components['schemas']['ReceiptImportListItemOut']
export type ReceiptDraft = components['schemas']['ReceiptImportDraftIn']
export type ReceiptConfirm = components['schemas']['ReceiptImportConfirmOut']
