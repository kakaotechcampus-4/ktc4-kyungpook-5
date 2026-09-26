import { Card } from '@/shared/ui/Card'
import { ProgressBar } from '@/shared/ui/ProgressBar'
import { formatCurrency } from '@/shared/lib/format'
import type { BudgetSummary } from '@/features/events/types'

interface BudgetStatusCardProps {
  // 합계는 GET /events/{id}, 설명은 ⏸ GET /events/{id}/budget 에서 온다.
  budget: BudgetSummary | null
  note: string
}

export function BudgetStatusCard({ budget, note }: BudgetStatusCardProps) {
  // 명세상 budget은 아직 null로 내려올 수 있다. 그때는 카드를 그리지 않는다.
  if (!budget) return null

  return (
    <Card className="flex w-full flex-col gap-[14px] p-[22px]">
      <p className="text-[13px] font-semibold text-[#242424]">예산 현황</p>

      <div className="flex w-full items-baseline gap-[6px]">
        <p className="text-[26px] font-bold whitespace-nowrap text-[#1c1c1c]">
          {budget.spent.toLocaleString('ko-KR')}
        </p>
        <p className="text-[13px] font-medium whitespace-nowrap text-[#737373]">
          / {formatCurrency(budget.planned)}
        </p>
      </div>

      <ProgressBar value={budget.spent} max={budget.planned} />

      <p className="text-[11.5px] text-[#737373]">{note}</p>
    </Card>
  )
}
