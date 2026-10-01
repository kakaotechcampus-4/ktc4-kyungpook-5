import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ProgressBar } from '@/shared/ui/ProgressBar'
import { formatCurrency } from '@/shared/lib/format'
import type { PaymentIssue, PaymentSummary } from '@/features/events/types'

interface PaymentStatusCardProps {
  // 합계는 GET /events/{id}, 미납·환불 목록은 ⏸ GET /events/{id}/payments 에서 온다.
  payment: PaymentSummary | null
  issues: PaymentIssue[]
}

// 수납 진행률과 미납·환불은 한 덩어리지만 시안에서 카드가 둘로 나뉜다.
export function PaymentStatusCard({ payment, issues }: PaymentStatusCardProps) {
  // 명세상 payment는 아직 null로 내려올 수 있다. 그때는 카드를 그리지 않는다.
  if (!payment) return null

  return (
    <>
      <Card className="flex w-full flex-col gap-[10px] rounded-[16px] p-[20px]">
        <p className="text-[13px] font-semibold text-[#242424]">수납</p>
        <ProgressBar value={payment.collected} max={payment.target} />
        <div className="flex w-full items-start gap-[8px]">
          <p className="text-[12px] font-medium whitespace-nowrap text-[#333]">
            {formatCurrency(payment.collected)} 걷힘
          </p>
          <div className="h-px flex-1" />
          <p className="text-[11.5px] whitespace-nowrap text-[#737373]">
            목표 {formatCurrency(payment.target)}
          </p>
        </div>
      </Card>

      <Card className="flex w-full flex-col overflow-hidden">
        <div className="flex w-full items-center gap-[8px] px-[20px] py-[15px]">
          <p className="text-[14px] font-semibold text-[#242424]">미납 · 환불</p>
          <div className="h-px flex-1" />
          <p className="text-[11.5px] whitespace-nowrap text-[#666]">
            납부 {payment.paidCount} / {payment.totalCount}명
          </p>
        </div>

        {issues.length === 0 ? (
          <p className="border-t border-[#ededed] px-[20px] py-[12px] text-[12px] text-[#737373]">
            미납·환불 건이 없습니다.
          </p>
        ) : (
          issues.map((issue) => (
            <div
              key={issue.id}
              className="flex w-full items-center gap-[12px] border-t border-[#ededed] px-[20px] py-[12px]"
            >
              <Chip variant={issue.kind === 'REFUND' ? 'attention' : 'subtle'}>
                {issue.kind === 'REFUND' ? '환불' : '미납'}
              </Chip>
              <div className="flex flex-col gap-[2px]">
                <p className="text-[12.5px] font-medium whitespace-nowrap text-[#333]">
                  {issue.name}
                </p>
                <p className="text-[11px] whitespace-nowrap text-[#7a7a7a]">{issue.note}</p>
              </div>
              <div className="h-px flex-1" />
              <p className="text-[11.5px] whitespace-nowrap text-[#666]">{issue.statusLabel}</p>
            </div>
          ))
        )}
      </Card>
    </>
  )
}
