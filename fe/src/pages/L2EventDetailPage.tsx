// L2 행사 상세 — 조립만 한다. 로직은 features/ 로.
import { useParams } from 'react-router-dom'
import { BudgetStatusCard } from '@/features/events/components/BudgetStatusCard'
import { ConfirmationRequestsCard } from '@/features/events/components/ConfirmationRequestsCard'
import { EventDetailHeader } from '@/features/events/components/EventDetailHeader'
import { PaymentStatusCard } from '@/features/events/components/PaymentStatusCard'
import { ResolvedApprovalsCard } from '@/features/events/components/ResolvedApprovalsCard'
import { StepProgressCard } from '@/features/events/components/StepProgressCard'
import { useEventDetail } from '@/features/events/hooks'

export default function L2EventDetailPage() {
  const { eventId = '' } = useParams()
  const {
    event,
    steps,
    confirmations,
    resolvedActions,
    resolvedTotalCount,
    budgetNote,
    paymentIssues,
    resolveConfirmation,
  } = useEventDetail(eventId)

  return (
    <div className="flex w-full flex-col gap-[16px] px-[26px] pt-[22px] pb-[28px]">
      <EventDetailHeader event={event} />
      <StepProgressCard steps={steps} />

      <div className="flex w-full items-start gap-[16px]">
        <div className="flex min-w-px flex-1 flex-col gap-[16px]">
          <ConfirmationRequestsCard requests={confirmations} onResolve={resolveConfirmation} />
          <ResolvedApprovalsCard actions={resolvedActions} totalCount={resolvedTotalCount} />
        </div>

        <div className="flex w-[400px] shrink-0 flex-col gap-[16px]">
          <BudgetStatusCard budget={event.budget} note={budgetNote} />
          <PaymentStatusCard payment={event.payment} issues={paymentIssues} />
        </div>
      </div>
    </div>
  )
}
