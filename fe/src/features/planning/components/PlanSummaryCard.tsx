// P2 우측 "이 계획 요약". GET /events/{eventId}/plan 의 summary를 그대로 읽는다.
import { Card } from '@/shared/ui/Card'
import { formatCurrency, formatMonthDay } from '@/shared/lib/format'
import { ACTOR_LABEL, ACTOR_UNIT } from '@/features/planning/labels'
import type { PlanSummary, StepActor } from '@/features/planning/types'

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex w-full items-center gap-[8px]">
      <p className="text-[12px] text-[#737373]">{label}</p>
      <div className="h-px flex-1" />
      <p className="text-[12.5px] font-medium whitespace-nowrap text-[#2e2e2e]">{value}</p>
    </div>
  )
}

export function PlanSummaryCard({ summary }: { summary: PlanSummary }) {
  const collection = summary.collectionPlan

  return (
    <Card className="flex w-full flex-col gap-[12px] p-[22px]">
      <p className="text-[13px] font-semibold text-[#242424]">이 계획 요약</p>

      <Row label="전체 단계" value={`${summary.totalSteps}개`} />
      {(Object.keys(ACTOR_LABEL) as StepActor[]).map((actor) => (
        <Row
          key={actor}
          label={ACTOR_LABEL[actor]}
          value={`${summary.countByActor[actor] ?? 0}${ACTOR_UNIT[actor]}`}
        />
      ))}
      <Row
        label="수금"
        value={
          collection
            ? `${collection.times}회 · 1인 ${formatCurrency(collection.feePerPerson)}`
            : '없음'
        }
      />
      <Row label="공지" value={`${summary.noticeCount}회`} />
      <Row
        label="기간"
        value={`${formatMonthDay(summary.periodStart)} → ${formatMonthDay(summary.periodEnd)}`}
      />
    </Card>
  )
}
