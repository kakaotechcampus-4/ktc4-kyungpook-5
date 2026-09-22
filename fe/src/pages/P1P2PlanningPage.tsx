// P1·P2 행사 계획 (1단계 챗봇 / 2단계 흐름 확정) — 조립만 한다. 로직은 features/ 로.
// 두 화면은 같은 Event 한 행을 다루므로 라우트도 페이지도 하나다(명세 §1).
import { useNavigate, useParams } from 'react-router-dom'
import { PlanChatBar, PlanChatCard } from '@/features/planning/components/PlanChat'
import { PlanConditionsCard } from '@/features/planning/components/PlanConditionsCard'
import { PlanDraftsCard } from '@/features/planning/components/PlanDraftsCard'
import { PlanActorLegend, PlanFlowCard } from '@/features/planning/components/PlanFlowCard'
import {
  PlanConfirmCard,
  PlanExcludedCard,
  PlanWarningsCard,
} from '@/features/planning/components/PlanReviewCards'
import { PlanStageBar } from '@/features/planning/components/PlanStageBar'
import { PlanSummaryCard } from '@/features/planning/components/PlanSummaryCard'
import { usePlanning } from '@/features/planning/hooks'
import { Button } from '@/shared/ui/Button'
import { formatCurrency, formatDateRange, formatMonthDay } from '@/shared/lib/format'

export default function P1P2PlanningPage() {
  const { eventId } = useParams()
  const navigate = useNavigate()
  const plan = usePlanning(eventId)

  // 2단계 머리말은 1단계에서 정한 값으로 만든다. plan 응답에는 인원·예산이 없다.
  const flowSubtitle = [
    plan.plan?.title ?? plan.title,
    plan.collected.headcount && `${plan.collected.headcount}명`,
    plan.collected.budgetTotal && `예산 ${formatCurrency(plan.collected.budgetTotal)}`,
    plan.plan &&
      `${formatMonthDay(plan.plan.summary.periodStart)} 준비 → ${formatMonthDay(plan.plan.summary.periodEnd)} 기록`,
  ]
    .filter(Boolean)
    .join(' · ')

  // TODO: POST /events/{eventId}:confirm — PLANNING → ON_GOING.
  function confirmPlan() {
    if (!window.confirm('이 계획으로 행사를 시작할까요? 1번 단계부터 진행됩니다.')) return
    navigate(`/events/${plan.eventId}`)
  }

  return (
    <div className="flex w-full flex-col gap-[16px] px-[26px] pt-[22px] pb-[28px]">
      <div className="flex w-full items-center gap-[10px]">
        <div className="flex flex-col gap-[2px]">
          <p className="text-[20px] font-bold text-[#212121]">행사 계획</p>
          <p className="text-[12px] text-[#737373]">
            {plan.stage === 'FLOW'
              ? flowSubtitle
              : `${plan.title} · ${plan.savedAt ? `${formatMonthDay(plan.savedAt)} 저장` : '아직 저장되지 않음'}`}
          </p>
        </div>

        <div className="h-px flex-1" />

        {plan.stage === 'FLOW' ? (
          <>
            <PlanActorLegend />
            <Button variant="secondary" size="pill" onClick={plan.backToChat}>
              1단계로 돌아가기
            </Button>
            <Button variant="secondary" size="pill" onClick={plan.save}>
              임시 저장
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" size="pill" onClick={plan.save}>
              임시 저장
            </Button>
            <Button variant="secondary" size="pill" onClick={plan.restart}>
              처음부터 다시
            </Button>
          </>
        )}
      </div>

      <PlanStageBar stage={plan.stage} />

      {plan.stage === 'FLOW' && plan.plan ? (
        <div className="flex w-full items-start gap-[16px]">
          <PlanFlowCard
            phases={plan.plan.phases}
            eventDaysLabel={formatDateRange(plan.collected.startDate, plan.collected.endDate)}
            onUpdateStep={plan.updateStep}
          />

          <div className="flex w-[330px] shrink-0 flex-col gap-[16px]">
            <PlanSummaryCard summary={plan.plan.summary} />
            <PlanWarningsCard warnings={plan.plan.warnings} onSuggestion={plan.addCheckpoint} />
            <PlanExcludedCard steps={plan.plan.excludedSteps} />
            <PlanConfirmCard onConfirm={confirmPlan} />
          </div>
        </div>
      ) : (
        <>
          <div className="flex w-full items-start gap-[16px]">
            <PlanChatCard
              turns={plan.turns}
              readyToGenerate={plan.readyToGenerate}
              pending={plan.pending}
              generating={plan.generating}
              onAsk={plan.ask}
              onGenerate={plan.generate}
            />

            <div className="flex w-[330px] shrink-0 flex-col gap-[14px]">
              <PlanConditionsCard collected={plan.collected} />
              <PlanDraftsCard drafts={plan.drafts} onResume={plan.resumeDraft} />
            </div>
          </div>

          <PlanChatBar pending={plan.pending} onAsk={plan.ask} />
        </>
      )}
    </div>
  )
}
