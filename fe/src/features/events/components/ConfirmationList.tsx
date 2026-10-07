// 확인 요청 카드(L2): 토리가 혼자 정하기 어려워 묻는 일. 되돌릴 수 있어 승인과 따로 둔다. 0건이면 빈 상태.
import type { EventAction } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'

interface ConfirmationListProps {
  actions: EventAction[]
  // choice는 options[].key, 직접 처리면 'MANUAL' (POST /actions/{id}/resolve 요청 값과 같다)
  onResolve: (action: EventAction, choice: string) => void
  className?: string
}

export function ConfirmationList({ actions, onResolve, className }: ConfirmationListProps) {
  const empty = actions.length === 0
  return (
    <Card className={cn('flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]', className)}>
      <div className="flex items-center gap-[9px]">
        <h2 className="text-h2">확인 요청</h2>
        <Chip tone={empty ? 'neutral' : 'approved'}>{actions.length}건</Chip>
        {!empty && <span className="text-caption text-mute">되돌릴 수 있어 승인은 아닙니다</span>}
      </div>

      {empty ? (
        <EmptyState
          variant="inline"
          toriSize={56}
          title="지금 확인할 일이 없어요"
          desc="토리가 혼자 정하기 어려운 일이 생기면 여기에 물어볼게요."
        />
      ) : (
        <ul className="flex flex-col gap-[18px]">
          {actions.map((action) => (
            <li
              key={action.id}
              className="flex flex-col gap-[10px] rounded-[14px] bg-bg px-[18px] py-[16px]"
            >
              <p className="text-[15px] font-bold">{action.title}</p>
              {action.subtitle && (
                <p className="text-[12.5px] leading-[19px] text-ink2">{action.subtitle}</p>
              )}
              {/* 첫 선택지가 토리가 가장 그럴듯하다고 본 답이라 파랗게 둔다 */}
              <div className="flex gap-[8px]">
                {(action.options ?? []).map((option, i) => (
                  <Button
                    key={option.key}
                    variant={i === 0 ? 'primary' : 'secondary'}
                    onClick={() => onResolve(action, option.key)}
                  >
                    {option.label}
                  </Button>
                ))}
                {action.allowManual && (
                  <Button variant="secondary" onClick={() => onResolve(action, 'MANUAL')}>
                    직접 처리
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
