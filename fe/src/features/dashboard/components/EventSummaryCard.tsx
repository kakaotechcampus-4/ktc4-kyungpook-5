// M1 행사 요약 카드: 행사 고르기(드롭다운) · 상태 / 행사일 · 장소 · 참가 · 현재 단계 · 출발까지 / 스테퍼 · 마감 D-day
import { StepStepper } from '@/features/events/components/StepStepper'
import type { EventStep, EventSummary } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { daysUntil, formatDateRange, formatDday, formatMonthDay } from '@/shared/lib/format'
import { EVENT_STATUS_LABEL } from '@/shared/lib/labels'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

interface EventSummaryCardProps {
  // 드롭다운에 띄울 행사들
  events: EventSummary[]
  selected: EventSummary
  onSelect: (eventId: string) => void
  steps: EventStep[]
}

export function EventSummaryCard({ events, selected, onSelect, steps }: EventSummaryCardProps) {
  const currentDeadline = steps.find((s) => s.state === 'CURRENT')?.deadline

  const meta = [
    { label: '행사일', value: formatDateRange(selected.startDate, selected.endDate) },
    { label: '장소', value: selected.location ?? '—' },
    { label: '참가', value: selected.headcount ? `${selected.headcount}명` : '—' },
    { label: '현재 단계', value: selected.currentStepName ?? '—', accent: true },
    { label: '출발까지', value: selected.dday !== null ? `${selected.dday}일` : '—' },
  ]

  return (
    <Card className="flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]">
      <div className="flex items-center gap-[11px]">
        {/* 브라우저 기본 select에 모양만 입힌다. 화살표는 위에 겹쳐 그린다. */}
        <div className="relative">
          <select
            aria-label="행사 선택"
            value={selected.id}
            onChange={(e) => onSelect(e.target.value)}
            className="cursor-pointer appearance-none rounded-[13px] border border-soft bg-bg py-[8px] pr-[38px] pl-[16px] text-[26px] font-bold [field-sizing:content] hover:bg-line"
          >
            {events.map((event) => (
              <option key={event.id} value={event.id}>
                {event.title}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute top-1/2 right-[14px] -translate-y-1/2 text-[15px] font-medium text-ink2">
            ▾
          </span>
        </div>
        <Chip tone="done">{EVENT_STATUS_LABEL[selected.status]}</Chip>
      </div>

      <dl className="flex gap-[36px]">
        {meta.map(({ label, value, accent }) => (
          <div key={label} className="flex flex-col gap-[5px]">
            <dt className="text-label text-mute">{label}</dt>
            <dd className={cn('text-[15px] font-bold', accent && 'text-blue-700')}>{value}</dd>
          </div>
        ))}
      </dl>

      {/* 단계가 아직 없으면(계획 확정 전) 구분선부터 통째로 숨긴다 */}
      {steps.length > 0 && (
        <>
          <hr className="border-line" />
          <div className="flex items-center gap-[24px]">
            <div className="min-w-0 flex-1">
              <StepStepper
                steps={steps.map((s) => ({
                  name: s.name,
                  date: s.deadline ? formatMonthDay(s.deadline) : undefined,
                  state: s.state,
                }))}
              />
            </div>
            {currentDeadline && (
              <div className="flex shrink-0 flex-col items-center gap-[1px] rounded-[14px] bg-blue-100 px-[22px] py-[15px]">
                <span className="text-display text-blue-700">
                  {formatDday(daysUntil(currentDeadline))}
                </span>
                <span className="text-label text-blue-600">마감까지</span>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  )
}
