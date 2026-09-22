// L1 행사 목록 — 조립만 한다. 로직은 features/ 로.
import { Link } from 'react-router-dom'
import { CompletedEventsCard } from '@/features/events/components/CompletedEventsCard'
import { DraftEventsCard } from '@/features/events/components/DraftEventsCard'
import { EventCard } from '@/features/events/components/EventCard'
import { useEventList } from '@/features/events/hooks'

export default function L1EventListPage() {
  const { ongoing, drafts, completedCount } = useEventList()

  return (
    <div className="flex w-full flex-col gap-[16px] px-[26px] pt-[22px] pb-[28px]">
      <div className="flex w-full items-center gap-[10px]">
        <div className="flex flex-col gap-[2px]">
          <p className="text-[20px] font-bold text-[#212121]">행사 목록</p>
          <p className="text-[12px] text-[#737373]">
            진행 중 {ongoing.length}건 · 계획 중 {drafts.length}건 · 끝난 행사 {completedCount}건
          </p>
        </div>
        <div className="h-px flex-1" />
        <Link
          to="/planning"
          className="inline-flex shrink-0 items-center rounded-[20px] border border-[#262626] bg-[#262626] px-[13px] py-[8px] text-[12px] font-medium whitespace-nowrap text-[#fafafa] transition-colors hover:bg-[#1a1a1a]"
        >
          + 새 행사 계획하기
        </Link>
      </div>

      <p className="text-[15px] font-semibold text-[#242424]">진행 중인 행사</p>

      {ongoing.length === 0 ? (
        <p className="text-[12.5px] text-[#737373]">진행 중인 행사가 없습니다.</p>
      ) : (
        ongoing.map((event) => <EventCard key={event.id} event={event} />)
      )}

      <div className="flex w-full items-start gap-[16px]">
        <DraftEventsCard drafts={drafts} />
        <CompletedEventsCard count={completedCount} />
      </div>
    </div>
  )
}
