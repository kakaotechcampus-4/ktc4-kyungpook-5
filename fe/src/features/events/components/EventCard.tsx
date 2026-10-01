import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { cn } from '@/shared/lib/cn'
import { formatCurrency, formatDateRange } from '@/shared/lib/format'
import type { EventListItem, StepState } from '@/features/events/types'

const STEP_BAR_CLASS: Record<StepState, string> = {
  DONE: 'bg-[#333]',
  CURRENT: 'bg-[#737373]',
  TODO: 'bg-[#e6e6e6]',
}

function metricsOf(event: EventListItem): string[] {
  // 참석 신청·설문 응답 수는 구글폼에 있어 BE가 모른다. 납부(transactions)만 표시한다.
  const payment = event.payment
    ? `${event.payment.totalCount}명 중 ${event.payment.paidCount}명 납부`
    : null
  const budget = event.budget
    ? `${formatCurrency(event.budget.planned)} 중 ${formatCurrency(event.budget.spent)} 집행`
    : null
  return [payment, budget].filter((text): text is string => Boolean(text))
}

export function EventCard({ event }: { event: EventListItem }) {
  const metrics = metricsOf(event)

  return (
    <Link to={`/events/${event.id}`} className="w-full">
      <Card className="flex w-full flex-col gap-[14px] p-[22px] transition-colors hover:border-[#d9d9d9]">
        <div className="flex w-full items-center gap-[10px]">
          <p className="text-[17px] font-bold whitespace-nowrap text-[#212121]">{event.title}</p>
          {event.currentStepName && <Chip>{event.currentStepName} 단계</Chip>}
          {event.pendingApprovalCount > 0 && (
            <Chip variant="attention">승인 대기 {event.pendingApprovalCount}건</Chip>
          )}
          <div className="h-px flex-1" />
          <p className="text-[12px] whitespace-nowrap text-[#6b6b6b]">
            {formatDateRange(event.startDate, event.endDate)}
          </p>
          {event.dday !== null && <Chip variant="subtle">D-{event.dday}</Chip>}
          <span className="text-[15px] font-medium text-[#808080]">›</span>
        </div>

        <div className="flex w-full items-start gap-[4px]">
          {event.stepProgress.map((step) => (
            <div
              key={step.stepOrder}
              className={cn('h-[6px] min-w-px flex-1 rounded-[3px]', STEP_BAR_CLASS[step.state])}
            />
          ))}
        </div>

        <div className="flex w-full items-center gap-[20px]">
          {metrics.map((text, i) => (
            <div key={text} className="flex items-center gap-[20px]">
              {i > 0 && <div className="h-[12px] w-px bg-[#e0e0e0]" />}
              <p className="text-[12px] whitespace-nowrap text-[#595959]">{text}</p>
            </div>
          ))}
          <div className="h-px flex-1" />
          <p className="text-[11.5px] font-medium whitespace-nowrap text-[#6b6b6b]">
            상세 진행 상황 보기
          </p>
        </div>
      </Card>
    </Link>
  )
}
