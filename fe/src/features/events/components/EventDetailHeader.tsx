import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { formatDateRange } from '@/shared/lib/format'
import type { EventDetail } from '@/features/events/types'

// 진행 상황 막대의 색이 무슨 뜻인지 알려주는 범례. 색은 StepProgressCard와 같은 값이다.
const LEGEND = [
  { label: 'AI 실행', dotClass: 'bg-[#5a7599]' },
  { label: '승인 필요', dotClass: 'bg-[#aa7c3a]' },
  { label: '직접 수행', dotClass: 'border-2 border-[#cdcdcd] bg-white' },
]

function subtitleOf(event: EventDetail): string {
  return [
    formatDateRange(event.startDate, event.endDate),
    event.location,
    event.headcount !== null ? `참가 ${event.headcount}명` : null,
    event.dday !== null ? `출발까지 ${event.dday}일` : null,
  ]
    .filter((part): part is string => Boolean(part))
    .join(' · ')
}

export function EventDetailHeader({ event }: { event: EventDetail }) {
  return (
    <div className="flex w-full items-center gap-[10px]">
      <div className="flex flex-col gap-[3px]">
        <Link to="/events" className="text-[11.5px] font-medium text-[#737373] hover:text-[#333]">
          ‹ 행사 목록
        </Link>

        <div className="flex items-center gap-[10px]">
          <p className="text-[22px] font-bold whitespace-nowrap text-[#1f1f1f]">{event.title}</p>
          {event.currentStep && <Chip>{event.currentStep.name} 단계</Chip>}

          <div className="flex shrink-0 items-center gap-[14px] rounded-[10px] border border-[#e0e0e0] bg-white px-[13px] py-[9px]">
            {LEGEND.map((item) => (
              <div key={item.label} className="flex items-center gap-[6px]">
                <span className={`size-[9px] shrink-0 rounded-full ${item.dotClass}`} />
                <span className="text-[10.5px] font-medium whitespace-nowrap text-[#595959]">
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[12px] whitespace-nowrap text-[#737373]">{subtitleOf(event)}</p>
      </div>

      <div className="h-px flex-1" />
      <Button variant="secondary" size="pill">
        계획 수정
      </Button>
      <Button variant="secondary" size="pill">
        행사 취소
      </Button>
    </div>
  )
}
