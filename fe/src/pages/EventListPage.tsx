// L1 행사 목록: 계획 중 · 진행 중 · 끝난 행사를 모두 본다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EventCard } from '@/features/events/components/EventCard'
import type { EventStatus, EventSummary } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'

type Filter = 'ALL' | EventStatus

const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: 'ALL', label: '전체' },
  { value: 'ON_GOING', label: '진행 중' },
  { value: 'PLANNING', label: '계획 중' },
  { value: 'COMPLETE', label: '완료' },
]

export default function EventListPage() {
  const navigate = useNavigate()
  const startPlanning = () => navigate('/planning')
  const [filter, setFilter] = useState<Filter>('ALL')

  // TODO: GET /events 연동 전까지는 빈 목록이다.
  const events: EventSummary[] = []

  const countOf = (value: Filter) =>
    value === 'ALL' ? events.length : events.filter((e) => e.status === value).length
  const shown = filter === 'ALL' ? events : events.filter((e) => e.status === filter)

  return (
    <div className="flex flex-col gap-[20px]">
      <header className="flex items-center justify-between">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">행사 목록</h1>
          <p className="text-mute">계획 중인 행사와 지난 행사를 모두 봅니다</p>
        </div>
        <Button size="lg" className="text-[13px]" onClick={startPlanning}>
          + 새 행사 만들기
        </Button>
      </header>

      {events.length === 0 ? (
        <EmptyState
          toriSize={96}
          title="아직 만든 행사가 없어요"
          desc="행사를 만들면 여기에 쌓여요. 끝난 행사 기록도 여기서 다시 볼 수 있어요."
          action={
            <Button size="lg" className="text-[13px]" onClick={startPlanning}>
              첫 행사 만들기
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex gap-[8px]">
            {FILTERS.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
                className={cn(
                  'rounded-[10px] border px-[14px] py-[9px] text-[12.5px]',
                  filter === value
                    ? 'border-blue-600 bg-blue-600 font-bold text-white'
                    : 'border-soft bg-card font-medium text-ink2 hover:bg-bg',
                )}
              >
                {label} {countOf(value)}
              </button>
            ))}
          </div>
          {shown.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </>
      )}
    </div>
  )
}
