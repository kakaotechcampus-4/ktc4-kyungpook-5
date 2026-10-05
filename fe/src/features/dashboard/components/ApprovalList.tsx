// 승인 대기 카드(M1): 결정이 필요한 Action을 한 줄씩 쌓는다. 0건이면 빈 상태 블록을 보인다.
import type { EventAction } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { daysUntil, formatDday, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'

// 마감이 이 날수 이하로 남으면 D-day를 주의색으로 칠한다
const URGENT_DAYS = 3

interface ApprovalRowProps {
  action: EventAction
  onApprove: (action: EventAction) => void
  onDeny: (action: EventAction) => void
}

export function ApprovalRow({ action, onApprove, onDeny }: ApprovalRowProps) {
  const days = action.dueDate ? daysUntil(action.dueDate) : null
  return (
    <li className="flex flex-col gap-[10px] border-t border-line px-[26px] py-[17px]">
      <div className="flex items-center justify-between">
        <div className="flex gap-[7px]">
          <Chip size="sm">{ACTION_TYPE_LABEL[action.type] ?? action.type}</Chip>
          <Chip size="sm" tone="pending">
            승인 대기
          </Chip>
        </div>
        {action.dueDate && days !== null && (
          <div className="flex items-center gap-[7px]">
            <span className="text-caption font-medium text-mute">
              마감 {formatMonthDay(action.dueDate)}
            </span>
            <span
              className={cn(
                'rounded-[7px] px-[8px] py-[4px] text-[11px] font-bold',
                days <= URGENT_DAYS ? 'bg-pending-bg text-pending' : 'bg-bg text-ink2',
              )}
            >
              {formatDday(days)}
            </span>
          </div>
        )}
      </div>
      <p className="text-[15px] leading-[22px] font-bold">{action.title}</p>
      {action.subtitle && <p className="text-[12px] leading-[18px] text-mute">{action.subtitle}</p>}
      <div className="flex gap-[8px]">
        <Button onClick={() => onApprove(action)}>승인</Button>
        <Button variant="secondary" onClick={() => onDeny(action)}>
          아니요
        </Button>
      </div>
    </li>
  )
}

interface ApprovalListProps {
  actions: EventAction[]
  onApprove: (action: EventAction) => void
  onDeny: (action: EventAction) => void
  className?: string
}

export function ApprovalList({ actions, onApprove, onDeny, className }: ApprovalListProps) {
  const empty = actions.length === 0
  return (
    <Card className={cn('flex flex-col', className)}>
      <div className="flex items-center justify-between px-[26px] pt-[24px] pb-[16px]">
        <div className="flex items-center gap-[9px]">
          <h2 className="text-h2">승인 대기</h2>
          <Chip tone={empty ? 'neutral' : 'approved'}>{actions.length}건</Chip>
        </div>
        {!empty && <span className="text-caption text-mute">승인하면 내 이름으로 기록됩니다</span>}
      </div>

      {empty ? (
        <div className="px-[26px] pt-[2px] pb-[26px]">
          <EmptyState
            variant="inline"
            toriSize={72}
            title="지금 승인할 일이 없어요"
            desc="되돌릴 수 없는 일이 생기면 여기에 올려드릴게요."
          />
        </div>
      ) : (
        <ul>
          {actions.map((action) => (
            <ApprovalRow key={action.id} action={action} onApprove={onApprove} onDeny={onDeny} />
          ))}
        </ul>
      )}
    </Card>
  )
}
