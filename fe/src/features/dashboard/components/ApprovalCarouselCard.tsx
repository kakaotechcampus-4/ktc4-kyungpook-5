import { Link } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { PendingActionRow } from '@/features/dashboard/components/PendingActionRow'
import { ProgressSteps } from '@/features/dashboard/components/ProgressSteps'
import type { EventSummary } from '@/features/dashboard/types'

interface ApprovalCarouselCardProps {
  events: EventSummary[]
  index: number
  onPrev: () => void
  onNext: () => void
  onApprove: (actionId: string) => void
  onDeny: (actionId: string) => void
  onApproveAll: (eventId: string) => void
  pendingActionsLoading?: boolean
  pendingActionsError?: boolean
}

export function ApprovalCarouselCard({
  events,
  index,
  onPrev,
  onNext,
  onApprove,
  onDeny,
  onApproveAll,
  pendingActionsLoading,
  pendingActionsError,
}: ApprovalCarouselCardProps) {
  const event = events[index]

  return (
    <div className="flex w-full items-center gap-[14px]">
      <button
        type="button"
        onClick={onPrev}
        className="flex size-[44px] shrink-0 items-center justify-center rounded-[22px] border border-[#dbdbdb] bg-white text-[16px] text-[#595959] shadow-[0px_2px_6px_0px_rgba(0,0,0,0.06)] hover:bg-[#f7f7f7]"
        aria-label="이전 행사"
      >
        ‹
      </button>

      <Card className="flex flex-1 flex-col gap-[18px] p-[26px]">
        <div className="flex w-full items-center gap-[10px]">
          <p className="text-[24px] font-bold text-[#1f1f1f]">{event.title}</p>
          <Chip>{event.statusLabel}</Chip>
          <div className="h-px flex-1" />
          <p className="text-[12px] text-[#6b6b6b]">{event.ddayLabel}</p>
          <Link
            to={`/events/${event.id}`}
            className="rounded-[20px] border border-[#dbdbdb] bg-white px-[12px] py-[7px] text-[12px] font-medium text-[#525252] hover:bg-[#f7f7f7]"
          >
            행사 상세 보기 ›
          </Link>
        </div>

        {pendingActionsError && (
          <p className="w-full rounded-[10px] bg-[#fcf2e5] px-[14px] py-[10px] text-[11.5px] text-[#8c6b3a]">
            승인 대기 목록을 불러오지 못했습니다. 예시 데이터를 보여주고 있습니다.
          </p>
        )}

        {pendingActionsLoading ? (
          <div className="flex w-full items-center justify-center rounded-[16px] border border-dashed border-[#dedede] bg-[#fbfbfb] px-[20px] py-[24px] text-[12.5px] text-[#8c8c8c]">
            승인 대기 목록을 불러오는 중...
          </div>
        ) : event.pendingActions.length > 0 ? (
          <div className="flex w-full flex-col overflow-hidden rounded-[16px] border-[1.5px] border-[#4d4d4d] bg-[#fbfbfb]">
            <div className="flex w-full items-center gap-[10px] bg-white px-[20px] py-[15px]">
              <p className="text-[15px] font-bold text-[#1f1f1f]">승인 대기 {event.pendingActions.length}건</p>
              <Chip variant="outline">되돌릴 수 없는 일만 올립니다</Chip>
              <div className="h-px flex-1" />
              <Button size="pill" onClick={() => onApproveAll(event.id)}>
                한 번에 처리
              </Button>
            </div>
            <div className="flex w-full items-center gap-[8px] bg-[#f9f9f9] px-[20px] py-[10px]">
              <p className="text-[11px] text-[#6b6b6b]">총무 권한으로 {event.pendingActions.length}건 모두 승인할 수 있습니다.</p>
              <div className="h-px flex-1" />
              <p className="text-[11px] text-[#808080]">승인하면 내 이름으로 기록됩니다</p>
            </div>
            {event.pendingActions.map((action) => (
              <PendingActionRow key={action.id} action={action} onApprove={onApprove} onDeny={onDeny} />
            ))}
          </div>
        ) : (
          <div className="flex w-full items-center justify-center rounded-[16px] border border-dashed border-[#dedede] bg-[#fbfbfb] px-[20px] py-[24px] text-[12.5px] text-[#8c8c8c]">
            지금 승인이 필요한 항목이 없습니다.
          </div>
        )}

        <div className="flex w-full flex-col gap-[5px] rounded-[14px] bg-[#f8f8f8] px-[18px] py-[14px]">
          <div className="flex w-full items-center gap-[8px]">
            <p className="text-[11.5px] font-semibold text-[#666]">이렇게 판단한 이유</p>
            <div className="h-px flex-1" />
            <button type="button" className="text-[11px] font-medium text-[#737373] hover:underline">
              자세히 ›
            </button>
          </div>
          <p className="text-[12.5px] text-[#4d4d4d]">{event.reasoning}</p>
        </div>

        {event.steps.length > 0 && <ProgressSteps steps={event.steps} scheduleNote={event.scheduleNote} />}

        <div className="flex w-full items-center justify-center gap-[8px]">
          <p className="text-[11px] font-medium text-[#737373]">
            {index + 1} / {events.length}
          </p>
          {events.map((e, i) => (
            <span
              key={e.id}
              className={cn('size-[7px] rounded-full', i === index ? 'bg-[#404040]' : 'bg-[#d9d9d9]')}
            />
          ))}
        </div>
      </Card>

      <button
        type="button"
        onClick={onNext}
        className="flex size-[44px] shrink-0 items-center justify-center rounded-[22px] border border-[#dbdbdb] bg-white text-[16px] text-[#595959] shadow-[0px_2px_6px_0px_rgba(0,0,0,0.06)] hover:bg-[#f7f7f7]"
        aria-label="다음 행사"
      >
        ›
      </button>
    </div>
  )
}
