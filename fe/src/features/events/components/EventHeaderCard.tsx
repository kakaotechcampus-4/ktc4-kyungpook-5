// L2 상단 카드: 제목 · 상태 · 계획 수정/행사 취소 / 행사일 · 장소 · 참가 · 현재 단계 · 담당 / 스테퍼 · N/M 단계 진행
import { StepStepper } from '@/features/events/components/StepStepper'
import type { EventDetail, EventStep } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatDateRange, formatMonthDay } from '@/shared/lib/format'
import { EVENT_STATUS_LABEL, EVENT_STATUS_TONE } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

interface EventHeaderCardProps {
  event: EventDetail
  steps: EventStep[]
}

export function EventHeaderCard({ event, steps }: EventHeaderCardProps) {
  // 진행 중인 단계까지 센다(완료 + 진행 중)
  const reached = steps.filter((s) => s.state !== 'TODO').length

  const meta = [
    { label: '행사일', value: formatDateRange(event.startDate, event.endDate) },
    { label: '장소', value: event.location ?? '—' },
    { label: '참가', value: event.headcount ? `${event.headcount}명` : '—' },
    { label: '현재 단계', value: event.currentStep?.name ?? '—', accent: true },
    { label: '담당', value: event.manager ?? '—' },
  ]

  return (
    <Card className="flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[11px]">
          <h1 className="text-[26px] font-bold">{event.title}</h1>
          <Chip tone={EVENT_STATUS_TONE[event.status]}>{EVENT_STATUS_LABEL[event.status]}</Chip>
        </div>
        {/* TODO: 계획 수정 화면 · 행사 취소 API가 생기면 연결한다 */}
        <div className="flex gap-[8px]">
          <Button variant="secondary">계획 수정</Button>
          <Button variant="secondary">행사 취소</Button>
        </div>
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
          <div className="flex items-center gap-[22px]">
            <div className="min-w-0 flex-1">
              <StepStepper
                steps={steps.map((s) => ({
                  name: s.name,
                  date: s.deadline ? formatMonthDay(s.deadline) : undefined,
                  state: s.state,
                }))}
              />
            </div>
            <div className="flex shrink-0 flex-col items-center gap-[1px] rounded-[14px] bg-blue-100 px-[22px] py-[15px]">
              <span className="text-[28px] font-bold text-blue-700">
                {reached} / {steps.length}
              </span>
              <span className="text-label text-blue-600">단계 진행</span>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}
