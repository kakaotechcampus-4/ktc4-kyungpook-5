// 도메인 타입 정의
export interface PendingAction {
  id: string
  typeLabel: string
  title: string
  subtitle: string
}

export type StepState = 'DONE' | 'CURRENT' | 'TODO'

export interface ProgressStep {
  name: string
  state: StepState
}

export interface EventSummary {
  id: string
  title: string
  statusLabel: string
  ddayLabel: string
  pendingActions: PendingAction[]
  reasoning: string
  totalSteps: number
  currentStepIndex: number
  scheduleNote: string
  steps: ProgressStep[]
}

export interface UpcomingTransaction {
  id: string
  date: string
  label: string
  statusLabel: 'confirmed' | 'pending' | 'expected'
  amount: number
}

export interface BudgetChartData {
  labels: string[]
  actualBalances: (number | null)[]
  planLine: (number | null)[]
  historicalLine: (number | null)[]
}

export interface BudgetForecast {
  hasHistory: boolean
  confirmedBalance: number
  confirmedBalanceNote: string
  planExpected: number
  historicalExpected: number
  diffNote: string
  upcomingTransactions: UpcomingTransaction[]
  chart: BudgetChartData
}
