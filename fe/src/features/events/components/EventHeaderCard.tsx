// L2 상단 카드: 제목 · 상태 · 계획 이어보기/행사 완료/행사 취소 / 행사일 · 장소 · 참가 · 현재 단계 · 담당 / 스테퍼 · N/M 단계 진행
// 계획 중에는 단계 진행이 시작되지 않아 현재 단계 · 스테퍼 · N/M을 그리지 않는다(#337).
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
  // 스테퍼에서 단계를 누르면(Step 모달)
  onSelectStep: (step: EventStep) => void
  onCancelEvent: () => void
  onViewCancellation: () => void
  onEditPlan: () => void
  onCompleteEvent?: () => void
}

export function EventHeaderCard({
  event,
  steps,
  onSelectStep,
  onCancelEvent,
  onViewCancellation,
  onEditPlan,
  onCompleteEvent,
}: EventHeaderCardProps) {
  const planning = event.status === 'PLANNING'
  // 진행 중인 단계까지 센다(완료 + 진행 중)
  const reached = steps.filter((s) => s.state !== 'TODO').length

  const meta = [
    { label: '행사일', value: formatDateRange(event.startDate, event.endDate) },
    { label: '장소', value: event.location ?? '—' },
    { label: '참가', value: event.headcount ? `${event.headcount}명` : '—' },
    ...(planning
      ? []
      : [{ label: '현재 단계', value: event.currentStep?.name ?? '—', accent: true }]),
  ]

  return (
    <Card className="flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-[11px]">
          {/* 계획 검토에서 운영을 시작하면 그 화면의 제목과 상태 칩이 이 자리로 옮겨 온다(index.css의 event-title) */}
          <h1 className="text-[26px] font-bold [view-transition-name:event-title]">{event.title}</h1>
          <Chip
            tone={EVENT_STATUS_TONE[event.status]}
            className="[view-transition-name:event-status]"
          >
            {EVENT_STATUS_LABEL[event.status]}
          </Chip>
        </div>
        <div className="flex flex-wrap gap-[8px]">
          {/* 계획 중 행사는 P2 계획 검토의 「운영 시작」에서 시작한다(#337) */}
          {planning && <Button onClick={onEditPlan}>계획 이어보기</Button>}
          {event.status === 'ON_GOING' && onCompleteEvent && (
            <Button onClick={onCompleteEvent}>행사 완료</Button>
          )}
          {/* 취소 정리(참가자 안내·예약 취소·환불)는 운영을 시작한 뒤에야 할 일이 생겨 진행 중에만 연다 */}
          {event.status === 'ON_GOING' && (
            <Button variant="secondary" onClick={onCancelEvent}>행사 취소</Button>
          )}
          {(event.status === 'CANCELLING' || event.status === 'CANCELLED') && (
            <Button variant="secondary" onClick={onViewCancellation}>취소 정리 보기</Button>
          )}
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
      {!planning && steps.length > 0 && (
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
                onSelect={(i) => onSelectStep(steps[i])}
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
