import { useState } from 'react'
import { Avatar } from '@/shared/ui/Avatar'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { cn } from '@/shared/lib/cn'
import { formatDateTime } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL, MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import type { ActionStatus, EventAction } from '@/features/events/types'

// APPROVED(승인만 됨)와 DONE(실행까지 끝남)은 화면에서 똑같이 "승인"으로 묶는다.
type Filter = 'ALL' | 'APPROVED' | 'DENIED'

const FILTERS: Array<{ key: Filter; label: string }> = [
  { key: 'ALL', label: '전체' },
  { key: 'APPROVED', label: '승인' },
  { key: 'DENIED', label: '거절' },
]

function matches(filter: Filter, status: ActionStatus): boolean {
  if (filter === 'ALL') return true
  if (filter === 'DENIED') return status === 'DENIED'
  return status !== 'DENIED'
}

interface ResolvedApprovalsCardProps {
  actions: EventAction[]
  totalCount: number
}

export function ResolvedApprovalsCard({ actions, totalCount }: ResolvedApprovalsCardProps) {
  const [filter, setFilter] = useState<Filter>('ALL')
  const rows = actions.filter((action) => matches(filter, action.status))
  const deniedCount = actions.filter((action) => action.status === 'DENIED').length

  return (
    <Card className="flex w-full flex-col overflow-hidden">
      <div className="flex w-full items-center gap-[10px] px-[22px] py-[15px]">
        <p className="text-[14px] font-semibold text-[#242424]">처리된 승인 · {totalCount}건</p>
        <div className="h-px flex-1" />
        <div className="flex shrink-0 items-start gap-[3px] rounded-[10px] bg-[#f1f1f1] p-[3px]">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
              aria-pressed={filter === item.key}
              className={cn(
                'rounded-[8px] px-[11px] py-[6px] text-[11px] font-medium',
                filter === item.key
                  ? 'border border-[#e6e6e6] bg-white text-[#262626]'
                  : 'text-[#737373]',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="border-t border-[#ededed] px-[22px] py-[14px] text-[12px] text-[#737373]">
          해당하는 내역이 없습니다.
        </p>
      ) : (
        rows.map((action) => {
          const denied = action.status === 'DENIED'

          return (
            <div
              key={action.id}
              className="flex w-full flex-col gap-[9px] border-t border-[#ededed] px-[22px] py-[14px]"
            >
              <div className="flex w-full items-center gap-[10px]">
                {denied ? (
                  <Chip variant="outline" className="border-[#999] text-[#4d4d4d]">
                    거절
                  </Chip>
                ) : (
                  <Chip>승인</Chip>
                )}
                <p
                  className={cn(
                    'text-[13px] font-medium whitespace-nowrap',
                    denied ? 'text-[#737373]' : 'text-[#2e2e2e]',
                  )}
                >
                  {action.title}
                </p>
                <Chip variant="attention">{ACTION_TYPE_LABEL[action.type] ?? action.type}</Chip>
                <div className="h-px flex-1" />

                {action.resolvedBy && (
                  <div className="flex shrink-0 items-center gap-[7px]">
                    <Avatar name={action.resolvedBy.name} size="sm" emphasis />
                    <div className="flex flex-col gap-px">
                      <p className="text-[11.5px] font-medium whitespace-nowrap text-[#404040]">
                        {action.resolvedBy.name} ·{' '}
                        {MEMBER_ROLE_LABEL[action.resolvedBy.role] ?? action.resolvedBy.role}
                      </p>
                      {action.resolvedAt && (
                        <p className="text-[10.5px] whitespace-nowrap text-[#808080]">
                          {formatDateTime(action.resolvedAt)}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {action.denyReason && (
                <div className="flex w-full flex-col gap-[3px] rounded-[10px] bg-[#f8f8f8] px-[14px] py-[11px]">
                  <p className="text-[10.5px] font-semibold text-[#6b6b6b]">거절 사유</p>
                  <p className="text-[11.5px] text-[#525252]">{action.denyReason}</p>
                </div>
              )}
            </div>
          )
        })
      )}

      <div className="flex w-full items-center gap-[8px] border-t border-[#ededed] px-[22px] py-[14px]">
        <p className="text-[11.5px] whitespace-nowrap text-[#808080]">
          승인 {totalCount}건 중 {rows.length}건 표시 · 거절 {deniedCount}건
        </p>
        <div className="h-px flex-1" />
        {/* TODO: 승인 전체 목록 화면이 생기면 링크로 바꾼다. 지금은 갈 곳이 없다. */}
        <p className="text-[11.5px] font-medium whitespace-nowrap text-[#6b6b6b]">전체 보기 ›</p>
      </div>
    </Card>
  )
}
