// L2 계획 중 모드(#337): 운영 전이라 진행 대신 계획 초안의 구성과 운영 시작 준비를 보여 준다.
// 시작은 P2 계획 검토의 「운영 시작」에서 한다. 시작 조건은 서버 규칙(시작일 · 단계 1개 이상)만 보여 준다.
import type { EventDetail, EventStep } from '@/features/events/types'
import { reviewGroups } from '@/features/planning/reviewModel'
import { cn } from '@/shared/lib/cn'
import { formatDateRange } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { EmptyState } from '@/shared/ui/EmptyState'

interface PlanningOverviewProps {
  event: EventDetail
  steps: EventStep[]
  // 계획 화면으로 간다. 초안이 없으면 조건 화면, 있으면 P2다(#325).
  onContinue: () => void
}

export function PlanningOverview({ event, steps, onContinue }: PlanningOverviewProps) {
  if (!steps.length) {
    return (
      <EmptyState
        title="아직 계획 초안이 없어요"
        desc="대화로 조건을 정하고 초안을 만들어 주세요."
        action={<Button onClick={onContinue}>계획 이어보기</Button>}
      />
    )
  }

  const readiness = [
    { label: `계획 단계 ${steps.length}개`, ready: true },
    event.startDate
      ? { label: `행사 시작일 ${formatDateRange(event.startDate, event.endDate)}`, ready: true }
      : { label: '행사 시작일 미정', ready: false },
  ]

  return (
    <div className="grid grid-cols-1 items-start gap-[20px] lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card className="flex flex-col gap-[16px] px-[26px] pt-[22px] pb-[24px]">
        <h2 className="text-h2 text-ink">{`계획 초안 ${steps.length}단계`}</h2>
        {reviewGroups(steps).map((group) => (
          <section key={group.name} className="flex flex-col gap-[8px]">
            <h3 className="text-label font-bold text-ink2">{`${group.name} ${group.steps.length}`}</h3>
            <ol className="flex flex-col gap-[6px]">
              {group.steps.map((step) => (
                <li key={step.id} className="rounded-[10px] bg-bg px-[12px] py-[8px] text-body text-ink">
                  {step.name}
                </li>
              ))}
            </ol>
          </section>
        ))}
      </Card>

      <Card className="flex flex-col gap-[14px] px-[22px] pt-[22px] pb-[22px]">
        <h2 className="text-h2 text-ink">운영 시작 준비</h2>
        <ul className="flex flex-col gap-[8px]">
          {readiness.map((item) => (
            <li key={item.label} className="flex items-center justify-between gap-3 text-body">
              <span className="text-ink">{item.label}</span>
              <span
                className={cn(
                  'shrink-0 rounded-full px-[9px] py-[2px] text-label font-bold',
                  item.ready ? 'bg-blue-100 text-blue-700' : 'bg-bg text-failed',
                )}
              >
                {item.ready ? '준비됨' : '필요'}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-caption text-mute">계획 검토에서 운영을 시작할 수 있어요.</p>
        <Button onClick={onContinue}>계획 검토로 가서 운영 시작</Button>
      </Card>
    </div>
  )
}
