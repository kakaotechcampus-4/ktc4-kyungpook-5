// 행사 카드(L1): 이름 · 상태 칩 / 일정 · 참가 · 단계 · 상태 / 세그먼트 진행 바. 누르면 L2 상세로 간다.
import { Link, useLocation } from 'react-router-dom'
import { SegmentBar } from '@/features/events/components/SegmentBar'
import type { EventSummary } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatDateRange } from '@/shared/lib/format'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { Chip } from '@/shared/ui/Chip'

// 상태 칸 문구: 진행 중이면 승인 대기 건수, 계획 중이면 몇 단계째인지, 끝났으면 정산 완료
function statusText(event: EventSummary, current: number): string {
  if (event.status === 'COMPLETE') return '정산 완료'
  if (event.status === 'PLANNING') return `계획 ${current}단계 진행 중`
  if (event.pendingApprovalCount > 0) return `승인 대기 ${event.pendingApprovalCount}건`
  return event.currentStepName ?? '진행 중'
}

export function EventCard({ event }: { event: EventSummary }) {
  // ?demo 같은 주소 뒤쪽을 상세로 이어 붙인다
  const { search } = useLocation()
  const states = event.stepProgress.map((s) => s.state)
  // 진행 중인 단계까지 센다(완료 + 진행 중)
  const current = states.filter((s) => s !== 'TODO').length
  const schedule = [formatDateRange(event.startDate, event.endDate), event.location]
    .filter(Boolean)
    .join(' · ')

  const meta = [
    { label: '일정', value: schedule },
    { label: '참가', value: event.headcount ? `${event.headcount}명` : '미정' },
    { label: '단계', value: `${current} / ${states.length}` },
    { label: '상태', value: statusText(event, current) },
  ]

  return (
    <Link
      to={`/events/${event.id}${search}`}
      className={cn(
        'flex flex-col gap-[14px] rounded-[18px] bg-card px-[26px] pt-[24px] pb-[26px] transition-colors',
        // 진행 중인 행사는 파란 테두리로 눈에 띄게
        event.status === 'ON_GOING'
          ? 'border-[1.5px] border-blue-200 hover:border-blue-300'
          : 'border border-line hover:border-soft',
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[10px]">
          <h2 className="text-[19px] font-bold">{event.title}</h2>
          <Chip tone={EVENT_STATUS_TONE[event.status]}>{EVENT_STATUS_LABEL[event.status]}</Chip>
          {event.status === 'ON_GOING' && event.pendingApprovalCount > 0 && (
            <Chip tone="pending">승인 대기 {event.pendingApprovalCount}건</Chip>
          )}
        </div>
        <span className="text-[12px] font-semibold text-blue-700">자세히 ›</span>
      </div>

      <dl className="flex gap-[34px]">
        {meta.map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-[5px]">
            <dt className="text-label text-mute">{label}</dt>
            <dd className="text-body-strong">{value}</dd>
          </div>
        ))}
      </dl>

      <SegmentBar states={states} muted={event.status === 'COMPLETE'} />
    </Link>
  )
}
