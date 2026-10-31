import type { components } from '@/shared/api/schema'

export type Expense = components['schemas']['ExpenseOut']
export type ExpensePageMeta = components['schemas']['PageMeta']
export type CreateExpenseInput = components['schemas']['ExpenseCreateIn']
export type UpdateExpenseInput = components['schemas']['ExpenseUpdateIn']
