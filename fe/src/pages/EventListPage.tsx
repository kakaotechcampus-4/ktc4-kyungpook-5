// L1 행사 목록: 계획 중 · 진행 중 · 끝난 행사를 모두 본다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { EventCard } from '@/features/events/components/EventCard'
import { useEvents } from '@/features/events/hooks'
import type { EventStatus, EventSummary } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { Skeleton } from '@/shared/ui/Skeleton'
import { Button } from '@/shared/ui/Button'
import { EmptyState } from '@/shared/ui/EmptyState'
import { ServerErrorScreen } from '@/shared/ui/StateScreen'

type Filter = 'ALL' | EventStatus

const FILTERS: Array<{ value: Filter; label: string }> = [
  { value: 'ALL', label: '전체' },
  { value: 'ON_GOING', label: '진행 중' },
  { value: 'PLANNING', label: '계획 중' },
  { value: 'COMPLETE', label: '완료' },
]

// 끝난 행사(완료·취소)는 뒤로 보낸다. 같은 묶음 안에서는 서버가 준 순서(시작일 순)를 지킨다.
// 취소 정리 중(CANCELLING)은 처리할 일이 남아 있어 앞에 둔다.
const isFinished = (e: EventSummary) => e.status === 'COMPLETE' || e.status === 'CANCELLED'

export default function EventListPage() {
  const navigate = useNavigate()
  const startPlanning = () => navigate('/planning')
  const [filter, setFilter] = useState<Filter>('ALL')

  const eventsQuery = useEvents()
  const events = [...(eventsQuery.data ?? [])].sort(
    (a, b) => Number(isFinished(a)) - Number(isFinished(b)),
  )

  const countOf = (value: Filter) =>
    value === 'ALL' ? events.length : events.filter((e) => e.status === value).length
  const shown = filter === 'ALL' ? events : events.filter((e) => e.status === filter)

  // 목록을 받기 전에 빈 상태를 그리면 "아직 만든 행사가 없어요"가 잠깐 깜빡인다.
  // 그렇다고 아무것도 안 그리면 흰 화면이라, 들어올 카드 자리를 미리 잡아 둔다.
  if (eventsQuery.isPending) return <EventListSkeleton />
  if (eventsQuery.isError) {
    return <ServerErrorScreen onRetry={() => eventsQuery.refetch()} onHome={() => navigate('/')} />
  }

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
          {shown.length === 0 ? (
            <EmptyState
              variant="inline"
              toriSize={72}
              title="이 상태인 행사가 없어요"
              desc="다른 상태를 골라 보세요."
            />
          ) : (
            shown.map((event) => <EventCard key={event.id} event={event} />)
          )}
        </>
      )}
    </div>
  )
}

// 실제 카드와 같은 테두리·여백·줄 높이를 쓴다. 들어올 때 줄이 밀리지 않게 하는 것이 목적이다.
function EventListSkeleton() {
  return (
    <div className="flex flex-col gap-[20px]" role="status" aria-busy>
      <span className="sr-only">행사 목록을 불러오고 있어요.</span>
      <header className="flex items-center justify-between">
        <div className="flex flex-col gap-[4px]">
          <h1 className="text-h1">행사 목록</h1>
          <p className="text-mute">계획 중인 행사와 지난 행사를 모두 봅니다</p>
        </div>
      </header>
      <div className="flex gap-[8px]">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[37px] w-[86px] rounded-[10px]" />
        ))}
      </div>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="flex flex-col gap-[14px] rounded-[18px] border border-line bg-card px-[26px] pt-[24px] pb-[26px]"
        >
          <Skeleton className="h-[26px] w-[220px]" />
          <Skeleton className="h-[17px] w-full max-w-[460px]" />
          <Skeleton className="h-[17px] w-full max-w-[380px]" />
        </div>
      ))}
    </div>
  )
}
