// 토리의 판단 카드(M1): 지금 무엇이 급한지와 그렇게 본 근거.
import type { ToriJudgement } from '@/features/dashboard/types'
import { cn } from '@/shared/lib/cn'
import { Card } from '@/shared/ui/Card'
import { ToriNote } from '@/shared/ui/ToriNote'

export function ToriJudgementCard({
  judgement,
  className,
}: {
  judgement: ToriJudgement
  className?: string
}) {
  return (
    <Card className={cn('flex flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]', className)}>
      <h2 className="text-h2">토리의 판단</h2>
      <ToriNote title={judgement.title}>{judgement.reason}</ToriNote>

      {judgement.evidence.length > 0 && (
        <div className="flex flex-col gap-[11px]">
          <h3 className="text-body font-bold text-ink2">확인한 근거</h3>
          <ul className="flex flex-col gap-[11px]">
            {judgement.evidence.map(({ label, source }) => (
              <li key={label} className="flex items-center gap-[10px]">
                <span className="size-[6px] shrink-0 rounded-full bg-blue-400" />
                <div className="flex flex-col gap-[2px]">
                  <span className="text-body-strong">{label}</span>
                  <span className="text-label font-normal text-mute">{source}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
