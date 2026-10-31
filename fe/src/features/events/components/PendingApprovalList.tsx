// L2 승인 대기: 지금 검토가 필요한 Action을 L2에서 바로 보인다.
// 전에는 단계를 눌러 Step 모달을 열어야만 보여서, 할 일이 있는 줄 모르고 지나쳤다.
import { ActionCard } from '@/features/events/components/ActionCard'
import type { EventAction } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'

interface PendingApprovalListProps {
  actions: EventAction[]
  // [검토하기]를 눌렀을 때. 결정 검토 모달은 화면 쪽에서 띄운다.
  // 끝난 행사에서는 주지 않는다 — 버튼 없이 무엇이 남았는지만 보인다.
  onReview?: (action: EventAction) => void
  className?: string
}

export function PendingApprovalList({ actions, onReview, className }: PendingApprovalListProps) {
  return (
    <Card className={cn('flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]', className)}>
      <div className="flex items-center gap-[9px]">
        <h2 className="text-h2">승인 대기</h2>
        {actions.length > 0 && (
          <Chip size="sm" tone="pending">
            {actions.length}건
          </Chip>
        )}
      </div>

      {actions.length === 0 ? (
        <EmptyState
          variant="inline"
          toriSize={56}
          title="지금 검토할 일이 없어요"
          desc="토리가 준비를 마치면 여기에서 승인을 받을게요."
        />
      ) : (
        <ul className="flex flex-col gap-[14px]">
          {actions.map((action) => (
            <li key={action.id}>
              <ActionCard action={action} onReview={onReview} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
