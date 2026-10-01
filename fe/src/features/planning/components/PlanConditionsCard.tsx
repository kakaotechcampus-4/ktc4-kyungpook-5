// P1 우측 "지금까지 정해진 것". 값은 서버가 대화에서 뽑아 주는 collected다.
import { Card } from '@/shared/ui/Card'
import { cn } from '@/shared/lib/cn'
import { collectedRows } from '@/features/planning/labels'
import type { PlanCollected } from '@/features/planning/types'

export function PlanConditionsCard({ collected }: { collected: PlanCollected }) {
  const rows = collectedRows(collected)
  const filled = rows.filter(([, value]) => value).length

  return (
    <Card className="flex w-full flex-col gap-[14px] p-[22px]">
      <div className="flex w-full items-center gap-[8px]">
        <p className="text-[13px] font-semibold text-[#242424]">지금까지 정해진 것</p>
        <div className="h-px flex-1" />
        <p className="text-[11px] text-[#808080]">
          {filled} / {rows.length}
        </p>
      </div>

      {rows.map(([label, value]) => (
        <div key={label} className="flex w-full items-center gap-[10px]">
          <span
            className={cn(
              'size-[7px] shrink-0 rounded-full',
              value ? 'bg-[#404040]' : 'bg-[#d9d9d9]',
            )}
          />
          <p className="w-[74px] shrink-0 text-[12px] text-[#737373]">{label}</p>
          <div className="h-px flex-1" />
          <p
            className={cn(
              'shrink-0 text-[12px] font-medium',
              value ? 'text-[#2e2e2e]' : 'text-[#8c8c8c]',
            )}
          >
            {value ?? '아직'}
          </p>
        </div>
      ))}

      <div className="h-px w-full bg-[#ebebeb]" />
      <p className="text-[11.5px] text-[#737373]">
        비워둔 항목은 다음 단계에서 정해도 됩니다. 그대로 두면 작년 기록을 씁니다.
      </p>
    </Card>
  )
}
