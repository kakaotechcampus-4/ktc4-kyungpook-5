import { cn } from '@/shared/lib/cn'
import type { ProgressStep } from '@/features/dashboard/types'

const BAR_CLASS = {
  DONE: 'bg-[#333]',
  CURRENT: 'bg-[#737373]',
  TODO: 'bg-[#e6e6e6]',
} as const

const LABEL_CLASS = {
  DONE: 'text-[#383838] font-medium',
  CURRENT: 'text-[#383838] font-medium',
  TODO: 'text-[#8c8c8c] font-normal',
} as const

export function ProgressSteps({ steps, scheduleNote }: { steps: ProgressStep[]; scheduleNote: string }) {
  return (
    <div className="flex w-full flex-col gap-[12px]">
      <div className="flex w-full items-center gap-[8px]">
        <p className="text-[11.5px] font-semibold text-[#666]">진행 단계</p>
        <div className="h-px flex-1" />
        <p className="text-[11.5px] text-[#737373]">{scheduleNote}</p>
      </div>
      <div className="flex w-full items-start gap-[6px]">
        {steps.map((step) => (
          <div key={step.name} className="flex flex-1 flex-col gap-[7px]">
            <div className={cn('h-[7px] w-full rounded-[4px]', BAR_CLASS[step.state])} />
            <p className={cn('text-[10.5px] whitespace-nowrap', LABEL_CLASS[step.state])}>{step.name}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
