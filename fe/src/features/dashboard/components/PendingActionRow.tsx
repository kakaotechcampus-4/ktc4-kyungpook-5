import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import type { PendingAction } from '@/features/dashboard/types'

interface PendingActionRowProps {
  action: PendingAction
  onApprove: (id: string) => void
  onDeny: (id: string) => void
}

export function PendingActionRow({ action, onApprove, onDeny }: PendingActionRowProps) {
  return (
    <div className="flex w-full items-center gap-[12px] border-t border-[#e6e6e6] px-[20px] py-[14px]">
      <Chip variant="subtle" className="bg-[#ededed]">
        {action.typeLabel}
      </Chip>
      <div className="flex flex-col gap-[2px]">
        <p className="text-[13.5px] font-medium text-[#262626]">{action.title}</p>
        <p className="text-[11.5px] text-[#7a7a7a]">{action.subtitle}</p>
      </div>
      <div className="h-px flex-1" />
      <Button size="pill" onClick={() => onApprove(action.id)}>
        승인
      </Button>
      <Button variant="secondary" size="pill" onClick={() => onDeny(action.id)}>
        아니에요
      </Button>
    </div>
  )
}
