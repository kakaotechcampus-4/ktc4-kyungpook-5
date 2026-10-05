// 처리된 승인 카드(L2): 승인·거절된 일을 최신순으로. 개수 칩은 전체 건수, 행은 최근 몇 건만 보인다.
import type { EventAction } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatDateTime } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL, MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'

interface ResolvedActionListProps {
  actions: EventAction[]
  totalCount: number
  className?: string
}

export function ResolvedActionList({ actions, totalCount, className }: ResolvedActionListProps) {
  const empty = actions.length === 0
  return (
    <Card className={cn('flex flex-col', className)}>
      <div className="flex items-center justify-between px-[26px] pt-[24px] pb-[15px]">
        <div className="flex items-center gap-[9px]">
          <h2 className="text-h2">처리된 승인</h2>
          <Chip>{totalCount}건</Chip>
        </div>
        {/* TODO: 처리된 승인 전체 목록 화면이 생기면 연결한다 */}
        {!empty && (
          <button type="button" className="text-[12px] font-semibold text-blue-700 hover:underline">
            전체 보기 ›
          </button>
        )}
      </div>

      {empty ? (
        <div className="px-[26px] pt-[2px] pb-[26px]">
          <EmptyState
            variant="inline"
            toriSize={56}
            title="아직 처리한 일이 없어요"
            desc="승인하거나 거절한 일이 여기에 쌓여요."
          />
        </div>
      ) : (
        <ul>
          {actions.map((action) => {
            // 승인한 뒤 실행까지 끝난 것(DONE)도 승인으로 보인다
            const denied = action.status === 'DENIED'
            return (
              <li
                key={action.id}
                className="flex items-center justify-between gap-[16px] border-t border-line px-[26px] py-[15px]"
              >
                <div className="flex min-w-0 items-center gap-[11px]">
                  <Chip size="sm" tone={denied ? 'failed' : 'done'}>
                    {denied ? '거절' : '승인'}
                  </Chip>
                  <span className="truncate text-[13.5px] font-semibold">{action.title}</span>
                  <Chip size="sm">{ACTION_TYPE_LABEL[action.type] ?? action.type}</Chip>
                </div>
                {action.resolvedBy && action.resolvedAt && (
                  <div className="flex shrink-0 flex-col items-end gap-[2px]">
                    <span className="text-caption font-semibold text-ink2">
                      {action.resolvedBy.name} · {MEMBER_ROLE_LABEL[action.resolvedBy.role]}
                    </span>
                    <span className="text-[10.5px] text-mute">
                      {formatDateTime(action.resolvedAt)}
                    </span>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
